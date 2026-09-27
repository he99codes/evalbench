"""Builds report payloads from stored results/evidence and the run's raw_output."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import EvaluationResult, EvaluationRun, RunStatus
from app.schemas.evaluation import EvaluationRunRead, EvidenceItemRead
from app.schemas.report import (
    CriterionSide,
    EvidenceEntry,
    ImprovementRead,
    PreferenceRead,
    ReportCriterionRow,
    ReportEvaluation,
    ReportRead,
    ReportRequirement,
    RequirementCheckRead,
    ResponseMismatchRead,
    ResponseSummary,
    RewardMismatchRead,
)
from app.services import NotFoundError
from app.services.evaluation_service import get_evaluation, get_run
from app.utils import scoring


def latest_completed_run(db: Session, evaluation_id: uuid.UUID) -> EvaluationRun:
    run = db.scalar(
        select(EvaluationRun)
        .where(EvaluationRun.evaluation_id == evaluation_id, EvaluationRun.status == RunStatus.COMPLETED)
        .order_by(EvaluationRun.completed_at.desc())
        .limit(1)
    )
    if run is None:
        raise NotFoundError("This evaluation has no completed run yet")
    return run


def build_report(db: Session, evaluation_id: uuid.UUID, run_id: uuid.UUID | None = None) -> ReportRead:
    evaluation = get_evaluation(db, evaluation_id)
    if run_id is not None:
        run = get_run(db, evaluation_id, run_id)
        if run.status != RunStatus.COMPLETED:
            raise NotFoundError(f"Run {run_id} is {run.status}; only completed runs have reports")
    else:
        run = latest_completed_run(db, evaluation_id)

    raw: dict[str, Any] = run.raw_output
    stages = raw["stages"]
    snapshot = raw["criteria_snapshot"]
    results = db.scalars(
        select(EvaluationResult)
        .where(EvaluationResult.run_id == run.id)
        .options(selectinload(EvaluationResult.evidence))
    ).all()
    by_key = {(str(r.criterion_id), r.response.value): r for r in results}

    comparison = stages["pairwise_comparison"]
    decisive = set(comparison["decisive_criteria"])
    shares = scoring.normalized_weights(
        [scoring.CriterionWeight(c["criterion_id"], c["weight"], c["scale_min"], c["scale_max"]) for c in snapshot]
    )

    def side(result: EvaluationResult, c: dict[str, Any]) -> CriterionSide:
        return CriterionSide(
            result_id=result.id,
            score=result.score,
            normalized_score=round(scoring.normalize(result.score, c["scale_min"], c["scale_max"]), 4),
            passed=result.passed,
            reasoning=result.reasoning,
            evidence=[EvidenceItemRead.model_validate(e) for e in result.evidence],
        )

    rows: list[ReportCriterionRow] = []
    evidence: dict[str, list[EvidenceEntry]] = {"A": [], "B": []}
    for c in snapshot:
        ra, rb = by_key[(c["criterion_id"], "A")], by_key[(c["criterion_id"], "B")]
        a, b = side(ra, c), side(rb, c)
        leader = "TIE" if a.normalized_score == b.normalized_score else ("A" if a.normalized_score > b.normalized_score else "B")
        rows.append(
            ReportCriterionRow(
                criterion_id=uuid.UUID(c["criterion_id"]),
                name=c["name"],
                description=c["description"],
                weight=c["weight"],
                weight_share=round(shares[c["criterion_id"]], 4),
                scale_min=c["scale_min"],
                scale_max=c["scale_max"],
                a=a,
                b=b,
                leader=leader,
                decisive=c["name"] in decisive,
            )
        )
        for label, result in (("A", ra), ("B", rb)):
            for e in result.evidence:
                evidence[label].append(
                    EvidenceEntry(
                        criterion_id=result.criterion_id,
                        criterion_name=c["name"],
                        score=result.score,
                        scale_max=c["scale_max"],
                        passed=result.passed,
                        quote=e.quote,
                        supports=e.supports,
                        location=e.location,
                    )
                )

    extraction = stages["requirement_extraction"]
    mismatch_stage = stages["reward_mismatch"]
    checks = {
        label: {c["requirement_id"]: c for c in mismatch_stage["compliance"][label]} for label in ("A", "B")
    }

    def check(label: str, req_id: str) -> RequirementCheckRead | None:
        c = checks[label].get(req_id)
        return RequirementCheckRead(satisfied=c["satisfied"], explanation=c["explanation"], quote=c["quote"]) if c else None

    requirements = [
        ReportRequirement(
            id=uuid.UUID(r["id"]),
            ref=r["ref"],
            type=r["type"],
            description=r["description"],
            mandatory=r["mandatory"],
            source_text=r["source_text"],
            compliance_a=check("A", r["id"]),
            compliance_b=check("B", r["id"]),
        )
        for r in extraction["requirements"]
    ]

    scores = raw["scores"]

    def summary(label: str) -> ResponseSummary:
        mine = [row.a if label == "A" else row.b for row in rows]
        mandatory = [r for r in requirements if r.mandatory]
        checks_for_label = [r.compliance_a if label == "A" else r.compliance_b for r in mandatory]
        return ResponseSummary(
            label=label,
            overall_score=scores[f"overall_score_{label.lower()}"],
            criteria_passed=sum(1 for s in mine if s.passed),
            criteria_total=len(mine),
            mandatory_satisfied=sum(1 for c in checks_for_label if c is not None and c.satisfied),
            mandatory_total=len(mandatory),
            compliance_rate=mismatch_stage["compliance_rate"][label],
        )

    mm = mismatch_stage["result"]
    improvement = stages["improvement"]["output"]
    return ReportRead(
        evaluation=ReportEvaluation.model_validate(evaluation, from_attributes=True),
        run=EvaluationRunRead.model_validate(run),
        requirements=requirements,
        ambiguities=extraction["ambiguities"],
        criteria=rows,
        summary_a=summary("A"),
        summary_b=summary("B"),
        preference=PreferenceRead(
            preferred_response=comparison["preferred_response"],
            reasoning=comparison["reasoning"],
            decisive_criteria=comparison["decisive_criteria"],
            candidate_order=run.candidate_order,
            score_leader=scores["score_leader"],
            agrees_with_scores=comparison["preferred_response"] == scores["score_leader"],
        ),
        improvement=ImprovementRead(
            target_response=improvement["target_response"], improvement=improvement["improvement"].strip()
        ),
        reward_mismatch=RewardMismatchRead(
            flagged=mm["flagged"],
            threshold=mm["threshold"],
            a=ResponseMismatchRead(**mm["responses"]["A"]),
            b=ResponseMismatchRead(**mm["responses"]["B"]),
            preferred_less_compliant=mm["preferred_less_compliant"],
            score_leader_less_compliant=mm["score_leader_less_compliant"],
            reasons=mm["reasons"],
        ),
        evidence_a=evidence["A"],
        evidence_b=evidence["B"],
    )


def export_json(db: Session, evaluation_id: uuid.UUID) -> dict[str, Any]:
    """Full export: the report plus the complete raw_output of the run (reproducibility)."""
    report = build_report(db, evaluation_id)
    run = db.get(EvaluationRun, report.run.id)
    return {
        "export_version": 1,
        "report": report.model_dump(mode="json"),
        "run_raw_output": run.raw_output if run else None,
    }


# ---------------------------------------------------------------------------
# Project analytics (Phase 8). Only evaluations with a current verdict (status
# COMPLETED) count, each through its latest completed run.
# ---------------------------------------------------------------------------


def project_analytics(db: Session, project_id: uuid.UUID) -> "ProjectAnalytics":
    from collections import Counter, defaultdict

    from sqlalchemy import func

    from app.models import Criterion, Evaluation, EvaluationStatus
    from app.schemas.report import (
        CriterionFailureStat,
        PreferenceCounts,
        PreferencePoint,
        ProjectAnalytics,
    )
    from app.services.project_service import get_project

    get_project(db, project_id)
    total = db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.project_id == project_id)) or 0
    completed = list(
        db.scalars(
            select(Evaluation).where(
                Evaluation.project_id == project_id, Evaluation.status == EvaluationStatus.COMPLETED
            )
        )
    )
    ids = [e.id for e in completed]
    # Ascending order: later runs overwrite earlier ones, leaving the latest per evaluation.
    latest_runs = (
        {
            r.evaluation_id: r
            for r in db.scalars(
                select(EvaluationRun)
                .where(EvaluationRun.evaluation_id.in_(ids), EvaluationRun.status == RunStatus.COMPLETED)
                .order_by(EvaluationRun.completed_at.asc())
            )
        }
        if ids
        else {}
    )

    preference = Counter(e.preferred_response.value for e in completed if e.preferred_response)
    scores_a = [e.overall_score_a for e in completed if e.overall_score_a is not None]
    scores_b = [e.overall_score_b for e in completed if e.overall_score_b is not None]

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    checks_total = checks_ok = mismatches = 0
    by_day: dict[str, Counter] = defaultdict(Counter)
    for evaluation in completed:
        run = latest_runs.get(evaluation.id)
        if run is None:
            continue
        stages = run.raw_output.get("stages", {})
        mandatory = {r["id"] for r in stages.get("requirement_extraction", {}).get("requirements", []) if r["mandatory"]}
        for label in ("A", "B"):
            for check in stages.get("reward_mismatch", {}).get("compliance", {}).get(label, []):
                if check["requirement_id"] in mandatory:
                    checks_total += 1
                    checks_ok += bool(check["satisfied"])
        if stages.get("reward_mismatch", {}).get("result", {}).get("flagged"):
            mismatches += 1
        if evaluation.preferred_response and run.completed_at:
            by_day[run.completed_at.date().isoformat()][evaluation.preferred_response.value] += 1

    criteria_stats: list[CriterionFailureStat] = []
    run_ids = [r.id for r in latest_runs.values()]
    if run_ids:
        rows = db.execute(
            select(
                EvaluationResult.criterion_id,
                Criterion.name,
                func.count(),
                func.count().filter(EvaluationResult.passed.is_(False)),
            )
            .join(Criterion, Criterion.id == EvaluationResult.criterion_id)
            .where(EvaluationResult.run_id.in_(run_ids))
            .group_by(EvaluationResult.criterion_id, Criterion.name)
        ).all()
        criteria_stats = sorted(
            (
                CriterionFailureStat(
                    criterion_id=cid, name=name, evaluated=n, failed=failed,
                    pass_rate=round(100 * (n - failed) / n, 2),
                )
                for cid, name, n, failed in rows
            ),
            key=lambda s: (-s.failed, s.name),
        )
    most_failing = criteria_stats[0] if criteria_stats and criteria_stats[0].failed > 0 else None

    return ProjectAnalytics(
        project_id=project_id,
        total_evaluations=total,
        completed_evaluations=len(completed),
        preference=PreferenceCounts(**preference),
        average_score_a=mean(scores_a),
        average_score_b=mean(scores_b),
        average_quality=mean(scores_a + scores_b),
        constraint_compliance_rate=round(100 * checks_ok / checks_total, 2) if checks_total else None,
        mandatory_checks_total=checks_total,
        mandatory_checks_satisfied=checks_ok,
        reward_mismatch_count=mismatches,
        most_common_failing_criterion=most_failing,
        criteria=criteria_stats,
        preference_over_time=[
            PreferencePoint(date=day, A=c["A"], B=c["B"], TIE=c["TIE"]) for day, c in sorted(by_day.items())
        ],
    )


# ---------------------------------------------------------------------------
# Evaluator agreement (Phase 9): compares two completed runs of one evaluation,
# e.g. two providers/models or two rubric versions. Computed only from stored
# results; nothing is estimated.
# ---------------------------------------------------------------------------


def evaluator_agreement(
    db: Session, evaluation_id: uuid.UUID, run_1_id: uuid.UUID, run_2_id: uuid.UUID
) -> "AgreementRead":
    from app.schemas.report import AgreementRead, AgreementRunInfo, CriterionAgreement
    from app.services import InvalidRequestError

    get_evaluation(db, evaluation_id)
    if run_1_id == run_2_id:
        raise InvalidRequestError("Choose two different runs to compare")
    runs = [get_run(db, evaluation_id, rid) for rid in (run_1_id, run_2_id)]
    for run in runs:
        if run.status != RunStatus.COMPLETED:
            raise InvalidRequestError(f"Run {run.id} is {run.status}; only completed runs can be compared")

    history = [
        r.id
        for r in db.scalars(
            select(EvaluationRun).where(EvaluationRun.evaluation_id == evaluation_id).order_by(EvaluationRun.created_at)
        )
    ]

    def info(run: EvaluationRun) -> AgreementRunInfo:
        scores = run.raw_output["scores"]
        return AgreementRunInfo(
            run_id=run.id,
            run_number=history.index(run.id) + 1,
            provider=run.provider,
            evaluator_model=run.evaluator_model,
            rubric_version=run.rubric_version,
            prompt_version=run.prompt_version,
            candidate_order=run.candidate_order,
            preferred_response=run.raw_output["stages"]["pairwise_comparison"]["preferred_response"],
            overall_score_a=scores["overall_score_a"],
            overall_score_b=scores["overall_score_b"],
        )

    def results(run: EvaluationRun) -> dict[tuple[str, str], EvaluationResult]:
        rows = db.scalars(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
        return {(str(r.criterion_id), r.response.value): r for r in rows}

    snapshots = [{c["criterion_id"]: c for c in run.raw_output["criteria_snapshot"]} for run in runs]
    res_1, res_2 = results(runs[0]), results(runs[1])
    shared = [cid for cid in snapshots[0] if cid in snapshots[1]]
    only_one = sorted(
        {snapshots[0][c]["name"] for c in snapshots[0] if c not in snapshots[1]}
        | {snapshots[1][c]["name"] for c in snapshots[1] if c not in snapshots[0]}
    )

    rows: list[CriterionAgreement] = []
    for cid in shared:
        c1, c2 = snapshots[0][cid], snapshots[1][cid]
        for label in ("A", "B"):
            r1, r2 = res_1[(cid, label)], res_2[(cid, label)]
            n1 = scoring.normalize(r1.score, c1["scale_min"], c1["scale_max"])
            n2 = scoring.normalize(r2.score, c2["scale_min"], c2["scale_max"])
            rows.append(
                CriterionAgreement(
                    criterion_id=uuid.UUID(cid),
                    name=c1["name"],
                    response=label,
                    score_1=r1.score,
                    score_2=r2.score,
                    scale_min=c1["scale_min"],
                    scale_max=c1["scale_max"],
                    normalized_difference=round(abs(n1 - n2), 4),
                    passed_1=r1.passed,
                    passed_2=r2.passed,
                    pass_agrees=r1.passed == r2.passed,
                )
            )

    run_1, run_2 = info(runs[0]), info(runs[1])
    preference_agrees = run_1.preferred_response == run_2.preferred_response
    pass_matches = sum(1 for r in rows if r.pass_agrees)
    return AgreementRead(
        evaluation_id=evaluation_id,
        run_1=run_1,
        run_2=run_2,
        same_rubric=run_1.rubric_version == run_2.rubric_version,
        same_prompt_version=run_1.prompt_version == run_2.prompt_version,
        same_evaluator=(run_1.provider, run_1.evaluator_model) == (run_2.provider, run_2.evaluator_model),
        preference_agrees=preference_agrees,
        criteria=rows,
        criteria_only_in_one_run=only_one,
        pass_fail_agreement=round(100 * pass_matches / len(rows), 2) if rows else None,
        mean_abs_score_difference=round(sum(r.normalized_difference for r in rows) / len(rows), 4) if rows else None,
        overall_score_difference_a=round(run_2.overall_score_a - run_1.overall_score_a, 2),
        overall_score_difference_b=round(run_2.overall_score_b - run_1.overall_score_b, 2),
        overall_agreement=round(100 * (pass_matches + int(preference_agrees)) / (len(rows) + 1), 2),
    )
