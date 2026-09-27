"""Report payload shape and correctness, independent of the pipeline tests."""

import json
from pathlib import Path

import pytest

from app.providers.mock_provider import MockLLMProvider
from app.services import NotFoundError, evaluation_service, report_service

DEMO = json.loads((Path(__file__).resolve().parents[2] / "data" / "demo" / "refund_example.json").read_text())
API = "/api/v1"


@pytest.fixture
def completed(api, db):
    project = api.create_project()
    criteria = [
        api.create_criterion(project["id"], c["name"], description=c["description"], weight=c["weight"])
        for c in DEMO["criteria"]
    ]
    e = DEMO["evaluation"]
    evaluation = api.create_evaluation(
        project["id"], criteria, prompt=e["prompt"], response_a=e["response_a"], response_b=e["response_b"]
    )
    provider = MockLLMProvider()
    run = evaluation_service.start_run(db, evaluation["id"], provider=provider)
    evaluation_service.execute_run(run.id, provider, sleep=lambda s: None)
    db.expire_all()
    return evaluation


def test_report_matches_stored_results_and_scoring(db, completed):
    from app.models import EvaluationResult
    from app.utils import scoring
    from sqlalchemy import select

    report = report_service.build_report(db, completed["id"])
    stored = {(str(r.criterion_id), r.response.value): r for r in db.scalars(select(EvaluationResult))}

    assert len(report.criteria) == len(DEMO["criteria"])
    for row in report.criteria:
        for label, side in (("A", row.a), ("B", row.b)):
            db_row = stored[(str(row.criterion_id), label)]
            assert side.result_id == db_row.id
            assert side.score == db_row.score and side.passed == db_row.passed
            assert side.reasoning == db_row.reasoning
            assert len(side.evidence) == len(db_row.evidence)
            expected_norm = scoring.normalize(db_row.score, row.scale_min, row.scale_max)
            assert side.normalized_score == round(expected_norm, 4)

    weights = [scoring.CriterionWeight(str(row.criterion_id), row.weight, row.scale_min, row.scale_max) for row in report.criteria]
    assert report.summary_a.overall_score == scoring.aggregate_score(weights, {str(r.criterion_id): r.a.score for r in report.criteria})
    # weight_share is rounded to 4dp per row, so the sum can drift by a few 1e-4 units.
    assert abs(sum(r.weight_share for r in report.criteria) - 1.0) < 1e-3


def test_report_requirements_and_evidence_are_grounded(completed, db):
    report = report_service.build_report(db, completed["id"])
    assert {r.ref for r in report.requirements} == {f"R{i}" for i in range(1, len(report.requirements) + 1)}
    for r in report.requirements:
        for check in (r.compliance_a, r.compliance_b):
            assert check is not None
            if check.quote:
                text = report.evaluation.response_a if check is r.compliance_a else report.evaluation.response_b
                assert check.quote in text
    for entries, text in ((report.evidence_a, report.evaluation.response_a), (report.evidence_b, report.evaluation.response_b)):
        assert entries
        for e in entries:
            assert e.quote in text


def test_report_summary_and_mismatch_are_internally_consistent(completed, db):
    report = report_service.build_report(db, completed["id"])
    for summary in (report.summary_a, report.summary_b):
        assert 0 <= summary.mandatory_satisfied <= summary.mandatory_total
        assert 0 <= summary.criteria_passed <= summary.criteria_total == len(report.criteria)
    mm = report.reward_mismatch
    assert mm.a.overall_score == report.summary_a.overall_score
    assert mm.b.overall_score == report.summary_b.overall_score
    assert mm.flagged == bool(mm.reasons)
    assert report.preference.agrees_with_scores == (
        report.preference.preferred_response == report.preference.score_leader
    )


def test_report_for_missing_run_or_evaluation_raises(completed, db):
    import uuid

    with pytest.raises(NotFoundError):
        report_service.build_report(db, uuid.uuid4())
    with pytest.raises(NotFoundError):
        report_service.build_report(db, completed["id"], uuid.uuid4())


def test_report_for_evaluation_with_no_run_raises(api, db):
    project = api.create_project()
    c = api.create_criterion(project["id"])
    evaluation = api.create_evaluation(project["id"], [c])
    with pytest.raises(NotFoundError):
        report_service.build_report(db, evaluation["id"])


def test_export_json_includes_report_and_raw_output(completed, db):
    export = report_service.export_json(db, completed["id"])
    assert export["export_version"] == 1
    assert export["report"]["evaluation"]["id"] == completed["id"]
    assert set(export["run_raw_output"]["stages"]) == {
        "requirement_extraction", "independent_evaluation", "pairwise_comparison", "improvement", "reward_mismatch",
    }


def test_report_by_specific_run_id_after_rerun(client, db, completed):
    first_report = client.get(f"{API}/evaluations/{completed['id']}/report").json()
    provider = MockLLMProvider()
    run2 = evaluation_service.start_run(db, completed["id"], provider=provider)
    evaluation_service.execute_run(run2.id, provider, sleep=lambda s: None)

    latest = client.get(f"{API}/evaluations/{completed['id']}/report").json()
    assert latest["run"]["id"] == str(run2.id)
    old = client.get(f"{API}/evaluations/{completed['id']}/report", params={"run_id": first_report["run"]["id"]}).json()
    assert old["run"]["id"] == first_report["run"]["id"] and old["run"]["id"] != latest["run"]["id"]

    run2_running = evaluation_service.start_run(db, completed["id"], provider=MockLLMProvider())
    r = client.get(f"{API}/evaluations/{completed['id']}/report", params={"run_id": run2_running.id})
    assert r.status_code == 404  # not COMPLETED
