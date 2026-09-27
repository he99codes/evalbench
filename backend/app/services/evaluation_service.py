"""Evaluation CRUD and the staged evaluation pipeline (orchestration of stages 1-5)."""

import copy
import hashlib
import json
import logging
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, utcnow
from app.models import (
    Criterion,
    Evaluation,
    EvaluationCriterion,
    EvaluationResult,
    EvaluationRun,
    EvaluationStatus,
    EvidenceItem,
    PreferredResponse,
    ResponseLabel,
    RunStatus,
)
from app.providers import get_llm_provider, get_retry_policy
from app.providers.base import LLMProvider, RetryPolicy, StructuredCallResult, call_structured
from app.schemas.evaluation import EvaluationCreate, EvaluationCriterionInput, EvaluationUpdate
from app.services import ConflictError, InvalidRequestError, NotFoundError, comparison_service, requirement_service
from app.services.evidence_service import ground_evidence
from app.services.project_service import get_project
from app.utils import scoring
from app.utils.validation import CriterionEvaluationOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_evaluations(
    db: Session,
    *,
    project_id: uuid.UUID | None = None,
    status: EvaluationStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Evaluation]:
    query = select(Evaluation).order_by(Evaluation.created_at.desc())
    if project_id is not None:
        query = query.where(Evaluation.project_id == project_id)
    if status is not None:
        query = query.where(Evaluation.status == status)
    return list(db.scalars(query.limit(limit).offset(offset)))


def get_evaluation(db: Session, evaluation_id: uuid.UUID) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise NotFoundError(f"Evaluation {evaluation_id} not found")
    return evaluation


def _build_criteria_links(
    db: Session, project_id: uuid.UUID, selection: list[EvaluationCriterionInput]
) -> list[EvaluationCriterion]:
    ids = [item.criterion_id for item in selection]
    found = {
        c.id: c
        for c in db.scalars(
            select(Criterion).where(Criterion.id.in_(ids), Criterion.project_id == project_id)
        )
    }
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise InvalidRequestError(
            f"Criteria not found in this project: {', '.join(missing)}"
        )
    disabled = [found[i].name for i in ids if not found[i].enabled]
    if disabled:
        raise InvalidRequestError(f"Disabled criteria cannot be selected: {', '.join(disabled)}")

    links = [
        EvaluationCriterion(
            criterion_id=item.criterion_id,
            weight=item.weight if item.weight is not None else found[item.criterion_id].weight,
        )
        for item in selection
    ]
    if sum(link.weight for link in links) <= 0:
        raise InvalidRequestError("At least one selected criterion must have a weight greater than 0")
    return links


def create_evaluation(db: Session, data: EvaluationCreate) -> Evaluation:
    get_project(db, data.project_id)
    links = _build_criteria_links(db, data.project_id, data.criteria)
    evaluation = Evaluation(
        project_id=data.project_id,
        title=data.title,
        prompt=data.prompt,
        response_a=data.response_a,
        response_b=data.response_b,
        status=EvaluationStatus.DRAFT,
        criteria_links=links,
    )
    db.add(evaluation)
    db.commit()
    return evaluation


def _clear_results_summary(evaluation: Evaluation) -> None:
    evaluation.preferred_response = None
    evaluation.final_reasoning = None
    evaluation.improvement = None
    evaluation.overall_score_a = None
    evaluation.overall_score_b = None


def update_evaluation(db: Session, evaluation_id: uuid.UUID, data: EvaluationUpdate) -> Evaluation:
    """Partial update.

    Changing content (prompt, responses, criteria) invalidates the current verdict:
    the summary fields are cleared and status returns to READY (requirements still
    valid) or DRAFT (prompt changed, requirements discarded). Past runs are kept.
    """
    evaluation = get_evaluation(db, evaluation_id)
    changes = data.model_dump(exclude_unset=True, exclude={"criteria"})
    content_fields = {"prompt", "response_a", "response_b"}
    content_changed = any(
        getattr(evaluation, f) != v for f, v in changes.items() if f in content_fields
    ) or data.criteria is not None

    if content_changed and evaluation.status == EvaluationStatus.RUNNING:
        raise ConflictError("Evaluation is running; wait for the run to finish before editing")

    prompt_changed = "prompt" in changes and changes["prompt"] != evaluation.prompt
    for field, value in changes.items():
        setattr(evaluation, field, value)

    if data.criteria is not None:
        new_links = _build_criteria_links(db, evaluation.project_id, data.criteria)
        evaluation.criteria_links.clear()
        db.flush()  # delete old links before inserting (unique evaluation_id+criterion_id)
        evaluation.criteria_links.extend(new_links)

    if content_changed:
        _clear_results_summary(evaluation)
        if prompt_changed:
            evaluation.requirements.clear()
        evaluation.status = (
            EvaluationStatus.READY if evaluation.requirements else EvaluationStatus.DRAFT
        )

    db.commit()
    db.refresh(evaluation)
    return evaluation


def delete_evaluation(db: Session, evaluation_id: uuid.UUID) -> None:
    evaluation = get_evaluation(db, evaluation_id)
    if evaluation.status == EvaluationStatus.RUNNING:
        raise ConflictError("Evaluation is running; it cannot be deleted until the run finishes")
    db.delete(evaluation)
    db.commit()


def ensure_no_running_evaluations(db: Session, *, project_id: uuid.UUID) -> None:
    running = db.scalar(
        select(
            exists().where(
                Evaluation.project_id == project_id,
                Evaluation.status == EvaluationStatus.RUNNING,
            )
        )
    )
    if running:
        raise ConflictError("Project has a running evaluation; wait for it to finish")


# ---------------------------------------------------------------------------
# Pipeline (Phase 5+). Five separate LLM stages, never combined:
#   1 requirement extraction  2 independent per-criterion scoring (A and B separately)
#   3 pairwise comparison      4 improvement      5 compliance -> reward-mismatch check
# ---------------------------------------------------------------------------

# Bump when any stage prompt template changes (stored on every run for reproducibility).
PROMPT_VERSION = "evalbench-prompts-v2"

CRITERION_TEMPLATE = """Evaluate ONE response against ONE criterion. You see only this response; judge it on its own merits.

<criterion name="{name}" scale_min="{scale_min}" scale_max="{scale_max}">
{description}
</criterion>

<requirements>
{requirements}
</requirements>

<prompt>
{prompt}
</prompt>

<response>
{response}
</response>

Return criterion (the criterion name), score (a number from {scale_min} to {scale_max}), passed (true if the response meets the criterion), reasoning (2-4 sentences) and evidence: 1-3 items, each with quote (a SHORT verbatim phrase of 5-20 words copied character-for-character from the response — do not paraphrase, truncate, or alter its formatting) and supports (what the quote shows for this criterion)."""

ScheduleFn = Callable[..., Any]


def criteria_snapshot(evaluation: Evaluation) -> list[dict[str, Any]]:
    return [
        {
            "criterion_id": str(link.criterion_id),
            "name": link.criterion.name,
            "description": link.criterion.description,
            "weight": link.weight,
            "scale_min": link.criterion.scale_min,
            "scale_max": link.criterion.scale_max,
        }
        for link in evaluation.criteria_links
    ]


def rubric_version(snapshot: list[dict[str, Any]]) -> str:
    """Deterministic hash of the exact rubric (criteria, descriptions, weights, scales)."""
    canonical = json.dumps(sorted(snapshot, key=lambda c: c["criterion_id"]), sort_keys=True)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()[:16]


def get_run(db: Session, evaluation_id: uuid.UUID, run_id: uuid.UUID) -> EvaluationRun:
    run = db.get(EvaluationRun, run_id)
    if run is None or run.evaluation_id != evaluation_id:
        raise NotFoundError(f"Run {run_id} not found for evaluation {evaluation_id}")
    return run


def list_runs(db: Session, evaluation_id: uuid.UUID) -> list[EvaluationRun]:
    get_evaluation(db, evaluation_id)
    return list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.evaluation_id == evaluation_id)
            .order_by(EvaluationRun.created_at)
        )
    )


def start_run(
    db: Session,
    evaluation_id: uuid.UUID,
    *,
    schedule: ScheduleFn | None = None,
    provider: LLMProvider | None = None,
) -> EvaluationRun:
    """Create a PENDING run with full reproducibility metadata and schedule execution.

    `schedule(fn, *args)` is e.g. FastAPI BackgroundTasks.add_task. When None, the caller
    is responsible for calling execute_run (used by the seed script and tests).
    """
    evaluation = get_evaluation(db, evaluation_id)
    if evaluation.status == EvaluationStatus.RUNNING:
        raise ConflictError("Evaluation is already running")
    snapshot = criteria_snapshot(evaluation)
    if not snapshot or sum(c["weight"] for c in snapshot) <= 0:
        raise InvalidRequestError("Evaluation needs at least one criterion with a weight above 0")

    provider = provider or get_llm_provider()
    run = EvaluationRun(
        evaluation_id=evaluation.id,
        evaluator_model=provider.model,
        provider=provider.name,
        rubric_version=rubric_version(snapshot),
        prompt_version=PROMPT_VERSION,
        status=RunStatus.PENDING,
        raw_output={
            "criteria_snapshot": snapshot,
            "progress": {"stage": "queued", "completed_steps": 0, "total_steps": 5 + 2 * len(snapshot)},
            "stages": {},
            "calls": [],
            "error": None,
        },
    )
    db.add(run)
    evaluation.status = EvaluationStatus.RUNNING
    db.commit()
    if schedule is not None:
        schedule(execute_run, run.id, provider)
    return run


class _RunTracker:
    """Keeps raw_output in memory and commits progress so pollers can follow the run."""

    def __init__(self, db: Session, run: EvaluationRun) -> None:
        self.db = db
        self.run = run
        self.raw: dict[str, Any] = copy.deepcopy(run.raw_output)
        self.raw.setdefault("stages", {})
        self.raw.setdefault("calls", [])
        self.stage: str | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.any_usage = False

    def begin(self, stage: str) -> None:
        self.stage = stage
        self.raw["progress"]["stage"] = stage
        self._flush()

    def step_done(self) -> None:
        self.raw["progress"]["completed_steps"] += 1
        self._flush()

    def record_call(self, call: StructuredCallResult, **context: Any) -> None:
        response = call.response
        if response.input_tokens is not None or response.output_tokens is not None:
            self.any_usage = True
            self.input_tokens += response.input_tokens or 0
            self.output_tokens += response.output_tokens or 0
        self.raw["calls"].append(
            {
                "stage": self.stage,
                **context,
                "attempts": call.attempts,
                "retried_errors": call.errors,
                "latency_ms": response.latency_ms,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "raw_text": response.raw_text,
            }
        )

    def _flush(self) -> None:
        self.run.raw_output = copy.deepcopy(self.raw)
        self.db.commit()


def _result_lines(snapshot: list[dict[str, Any]], scored: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": c["name"],
            "weight": c["weight"],
            "scale_min": c["scale_min"],
            "scale_max": c["scale_max"],
            "score": scored[c["criterion_id"]]["score"],
            "passed": scored[c["criterion_id"]]["passed"],
            "reasoning": scored[c["criterion_id"]]["reasoning"],
        }
        for c in snapshot
    ]


def _score_criterion(
    provider: LLMProvider,
    criterion: dict[str, Any],
    *,
    requirements_text: str,
    prompt: str,
    response_text: str,
    label: ResponseLabel,
    policy: RetryPolicy,
    sleep: Callable[[float], None],
) -> StructuredCallResult:
    lo, hi = criterion["scale_min"], criterion["scale_max"]

    def postprocess(output: CriterionEvaluationOutput) -> dict[str, Any]:
        if not lo <= output.score <= hi:
            raise ValueError(f"score {output.score} outside scale {lo}-{hi}")
        if not output.reasoning.strip():
            raise ValueError("empty reasoning")
        evidence = ground_evidence(response_text, label, output.evidence)  # raises if none verbatim
        return {
            "criterion_id": criterion["criterion_id"],
            "response": label.value,
            "score": float(output.score),
            "passed": output.passed,
            "reasoning": output.reasoning.strip(),
            "evidence": [e.model_dump(mode="json") for e in evidence],
        }

    return call_structured(
        provider,
        CRITERION_TEMPLATE.format(
            name=criterion["name"],
            description=criterion["description"] or criterion["name"],
            scale_min=lo,
            scale_max=hi,
            requirements=requirements_text,
            prompt=prompt,
            response=response_text,
        ),
        CriterionEvaluationOutput,
        system=requirement_service.SYSTEM_PROMPT,
        postprocess=postprocess,
        policy=policy,
        sleep=sleep,
    )


def _run_pipeline(
    evaluation: Evaluation,
    tracker: _RunTracker,
    provider: LLMProvider,
    policy: RetryPolicy,
    rng: random.Random | None,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    raw = tracker.raw
    snapshot: list[dict[str, Any]] = raw["criteria_snapshot"]
    texts = {ResponseLabel.A: evaluation.response_a, ResponseLabel.B: evaluation.response_b}

    # Stage 1 -------------------------------------------------------------
    tracker.begin("requirement_extraction")
    extracted = requirement_service.extract_requirements(
        provider, evaluation.prompt, policy=policy, sleep=sleep
    )
    tracker.record_call(extracted.call)
    raw["stages"]["requirement_extraction"] = {
        "output": extracted.call.output.model_dump(),
        "requirements": extracted.requirements,
        "ambiguities": extracted.ambiguities,
    }
    tracker.step_done()
    requirements_text = requirement_service.format_requirements(extracted.requirements)

    # Stage 2: each response scored independently; A's call never sees B and vice versa.
    tracker.begin("independent_evaluation")
    scored: dict[str, dict[str, dict[str, Any]]] = {"A": {}, "B": {}}
    raw["stages"]["independent_evaluation"] = {"A": [], "B": []}
    for label in (ResponseLabel.A, ResponseLabel.B):
        for criterion in snapshot:
            call = _score_criterion(
                provider,
                criterion,
                requirements_text=requirements_text,
                prompt=evaluation.prompt,
                response_text=texts[label],
                label=label,
                policy=policy,
                sleep=sleep,
            )
            tracker.record_call(call, response=label.value, criterion_id=criterion["criterion_id"])
            scored[label.value][criterion["criterion_id"]] = call.processed
            raw["stages"]["independent_evaluation"][label.value].append(
                {"criterion_id": criterion["criterion_id"], "output": call.output.model_dump()}
            )
            tracker.step_done()

    # Deterministic aggregation from stored criterion scores and weights.
    weights = [
        scoring.CriterionWeight(c["criterion_id"], c["weight"], c["scale_min"], c["scale_max"])
        for c in snapshot
    ]
    overall = {
        label: scoring.aggregate_score(weights, {cid: r["score"] for cid, r in scored[label].items()})
        for label in ("A", "B")
    }
    leader = scoring.score_leader(overall["A"], overall["B"])
    raw["scores"] = {"overall_score_a": overall["A"], "overall_score_b": overall["B"], "score_leader": leader}
    lines = {label: _result_lines(snapshot, scored[label]) for label in ("A", "B")}

    # Stage 3: pairwise, only after both are scored; candidate order randomized.
    tracker.begin("pairwise_comparison")
    order = comparison_service.choose_candidate_order(rng)
    comparison = comparison_service.compare(
        provider,
        prompt=evaluation.prompt,
        response_a=evaluation.response_a,
        response_b=evaluation.response_b,
        results_a=lines["A"],
        results_b=lines["B"],
        order=order,
        policy=policy,
        sleep=sleep,
    )
    tracker.record_call(comparison.call, candidate_order=order)
    raw["stages"]["pairwise_comparison"] = {
        "candidate_order": order,
        "output": comparison.call.output.model_dump(),
        "preferred_response": comparison.preferred_response,
        "reasoning": comparison.reasoning,
        "decisive_criteria": comparison.decisive_criteria,
    }
    tracker.step_done()

    # Stage 4 -------------------------------------------------------------
    tracker.begin("improvement")
    improvement = comparison_service.suggest_improvement(
        provider,
        prompt=evaluation.prompt,
        response_a=evaluation.response_a,
        response_b=evaluation.response_b,
        results_a=lines["A"],
        results_b=lines["B"],
        preferred=comparison.preferred_response,
        policy=policy,
        sleep=sleep,
    )
    tracker.record_call(improvement)
    raw["stages"]["improvement"] = {"output": improvement.output.model_dump()}
    tracker.step_done()

    # Stage 5: per-requirement compliance per response, then deterministic mismatch check.
    tracker.begin("reward_mismatch")
    compliance: dict[str, list[dict[str, Any]]] = {}
    for label in (ResponseLabel.A, ResponseLabel.B):
        if extracted.requirements:
            call = requirement_service.check_compliance(
                provider, extracted.requirements, texts[label], policy=policy, sleep=sleep
            )
            tracker.record_call(call, response=label.value)
            compliance[label.value] = call.processed
        else:
            compliance[label.value] = []
        tracker.step_done()
    mandatory_ids = {r["id"] for r in extracted.requirements if r["mandatory"]}
    rates = {
        label: scoring.compliance_rate(
            [c["satisfied"] for c in compliance[label] if c["requirement_id"] in mandatory_ids]
        )
        for label in ("A", "B")
    }
    mismatch = scoring.detect_reward_mismatch(
        overall_a=overall["A"],
        overall_b=overall["B"],
        compliance_a=rates["A"],
        compliance_b=rates["B"],
        preferred=comparison.preferred_response,
    )
    raw["stages"]["reward_mismatch"] = {
        "compliance": compliance,
        "compliance_rate": rates,
        "result": asdict(mismatch),
    }

    return {
        "requirements": extracted.requirements,
        "scored": scored,
        "overall": overall,
        "comparison": comparison,
        "improvement": improvement.output,
    }


def execute_run(
    run_id: uuid.UUID,
    provider: LLMProvider,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    policy: RetryPolicy | None = None,
    rng: random.Random | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Execute a PENDING run. Results are written in one transaction at the end; any
    failure marks the run and evaluation FAILED with the error recorded (never a fake success)."""
    policy = policy or get_retry_policy()
    started = time.monotonic()
    with session_factory() as db:
        run = db.get(EvaluationRun, run_id)
        if run is None or run.status != RunStatus.PENDING:
            logger.warning("Run %s not found or not pending; skipping", run_id)
            return
        evaluation = run.evaluation
        run.status = RunStatus.RUNNING
        tracker = _RunTracker(db, run)
        try:
            outcome = _run_pipeline(evaluation, tracker, provider, policy, rng, sleep)
            _persist_outcome(db, evaluation, run, tracker, outcome, started)
            db.commit()
            logger.info("Run %s completed", run_id)
        except Exception as exc:  # noqa: BLE001 - every failure must be recorded, never swallowed
            logger.exception("Run %s failed at stage %s", run_id, tracker.stage)
            db.rollback()
            _mark_failed(db, run_id, tracker, exc, started)
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                close()


def _persist_outcome(
    db: Session,
    evaluation: Evaluation,
    run: EvaluationRun,
    tracker: _RunTracker,
    outcome: dict[str, Any],
    started: float,
) -> None:
    evaluation.requirements.clear()
    db.flush()
    evaluation.requirements.extend(
        requirement_service.requirement_rows(evaluation.id, outcome["requirements"])
    )
    for label in ("A", "B"):
        for result in outcome["scored"][label].values():
            db.add(
                EvaluationResult(
                    evaluation_id=evaluation.id,
                    run_id=run.id,
                    criterion_id=uuid.UUID(result["criterion_id"]),
                    response=ResponseLabel(label),
                    score=result["score"],
                    passed=result["passed"],
                    reasoning=result["reasoning"],
                    evidence=[
                        EvidenceItem(
                            response=ResponseLabel(label),
                            quote=e["quote"],
                            supports=e["supports"],
                            location=e["location"],
                        )
                        for e in result["evidence"]
                    ],
                )
            )
    comparison = outcome["comparison"]
    improvement = outcome["improvement"]
    evaluation.preferred_response = PreferredResponse(comparison.preferred_response)
    evaluation.final_reasoning = comparison.reasoning
    evaluation.improvement = improvement.improvement.strip()
    evaluation.overall_score_a = outcome["overall"]["A"]
    evaluation.overall_score_b = outcome["overall"]["B"]
    evaluation.status = EvaluationStatus.COMPLETED

    tracker.raw["progress"]["stage"] = "completed"
    run.raw_output = copy.deepcopy(tracker.raw)
    run.candidate_order = comparison.candidate_order
    run.status = RunStatus.COMPLETED
    run.completed_at = utcnow()
    run.latency_ms = int((time.monotonic() - started) * 1000)
    run.input_tokens = tracker.input_tokens if tracker.any_usage else None
    run.output_tokens = tracker.output_tokens if tracker.any_usage else None


def _mark_failed(
    db: Session, run_id: uuid.UUID, tracker: _RunTracker, exc: Exception, started: float
) -> None:
    run = db.get(EvaluationRun, run_id)
    if run is None:
        return
    raw = copy.deepcopy(tracker.raw)
    raw["progress"]["stage"] = "failed"
    raw["error"] = {
        "stage": tracker.stage,
        "type": type(exc).__name__,
        "message": str(exc)[:2000],
        "attempts": getattr(exc, "attempts", None),
        "retried_errors": getattr(exc, "errors", None),
    }
    run.raw_output = raw
    run.status = RunStatus.FAILED
    run.completed_at = utcnow()
    run.latency_ms = int((time.monotonic() - started) * 1000)
    run.input_tokens = tracker.input_tokens if tracker.any_usage else None
    run.output_tokens = tracker.output_tokens if tracker.any_usage else None
    candidate = raw.get("stages", {}).get("pairwise_comparison", {}).get("candidate_order")
    run.candidate_order = candidate
    run.evaluation.status = EvaluationStatus.FAILED
    db.commit()


def recover_interrupted_runs(session_factory: Callable[[], Session] = SessionLocal) -> int:
    """On startup: runs left PENDING/RUNNING by a crash/restart are marked FAILED."""
    with session_factory() as db:
        runs = list(
            db.scalars(
                select(EvaluationRun).where(
                    EvaluationRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING])
                )
            )
        )
        for run in runs:
            raw = copy.deepcopy(run.raw_output or {})
            raw["error"] = {
                "stage": (raw.get("progress") or {}).get("stage"),
                "type": "Interrupted",
                "message": "The server restarted before this run finished. Start a new run.",
            }
            run.raw_output = raw
            run.status = RunStatus.FAILED
            run.completed_at = utcnow()
            if run.evaluation.status == EvaluationStatus.RUNNING:
                run.evaluation.status = EvaluationStatus.FAILED
        db.commit()
        return len(runs)
