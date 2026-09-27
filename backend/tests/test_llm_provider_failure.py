"""Unrecoverable provider failures must end in FAILED, never in a fabricated result."""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import Evaluation, EvaluationResult, EvaluationRun, EvaluationStatus, EvidenceItem, RunStatus
from app.providers.base import LLMPermanentError, LLMResponse, LLMTimeoutError, RetryPolicy
from app.providers.mock_provider import MockLLMProvider
from app.services import evaluation_service
from app.utils.validation import (
    ComplianceCheckOutput,
    CriterionEvaluationOutput,
    PairwiseComparisonOutput,
    RequirementExtractionOutput,
)

DEMO = json.loads((Path(__file__).resolve().parents[2] / "data" / "demo" / "refund_example.json").read_text())
FAST = RetryPolicy(max_attempts=3, rate_limit_max_attempts=4, base_delay_s=0, max_delay_s=0)


@pytest.fixture
def evaluation(api):
    project = api.create_project()
    criteria = [api.create_criterion(project["id"], n) for n in ("Accuracy", "Tone")]
    e = DEMO["evaluation"]
    return api.create_evaluation(
        project["id"], criteria, prompt=e["prompt"], response_a=e["response_a"], response_b=e["response_b"]
    )


class FailingAt(MockLLMProvider):
    """Behaves like the mock except for one stage schema, where it misbehaves."""

    def __init__(self, schema, mode):
        super().__init__()
        self.target, self.mode, self.calls = schema, mode, 0

    def generate_structured(self, prompt, schema, *, system=None):
        if schema is not self.target:
            return super().generate_structured(prompt, schema, system=system)
        self.calls += 1
        if self.mode == "permanent":
            raise LLMPermanentError("401 invalid api key")
        if self.mode == "timeout":
            raise LLMTimeoutError("read timed out")
        if self.mode == "malformed":
            return LLMResponse(data={"unexpected": "shape"}, raw_text='{"unexpected": "shape"}')
        if self.mode == "fake_evidence":
            good = super().generate_structured(prompt, schema, system=system)
            good.data["evidence"] = [{"quote": "This sentence is not in the response.", "supports": "invented"}]
            return good
        if self.mode == "out_of_scale":
            good = super().generate_structured(prompt, schema, system=system)
            good.data["score"] = 11
            return good
        raise AssertionError(self.mode)


def _run(db, evaluation_id, provider):
    run = evaluation_service.start_run(db, evaluation_id, provider=provider)
    evaluation_service.execute_run(run.id, provider, policy=FAST, sleep=lambda s: None)
    db.expire_all()
    return db.get(EvaluationRun, run.id)


def _assert_failed_cleanly(db, run, stage, error_type="LLMCallFailedError"):
    assert run.status == RunStatus.FAILED
    assert run.completed_at is not None
    error = run.raw_output["error"]
    assert error["stage"] == stage and error["type"] == error_type and error["message"]
    evaluation = db.get(Evaluation, run.evaluation_id)
    assert evaluation.status == EvaluationStatus.FAILED
    # Nothing fabricated: no verdict, no scores, no results, no evidence.
    assert evaluation.preferred_response is None and evaluation.overall_score_a is None
    assert evaluation.final_reasoning is None and evaluation.improvement is None
    assert db.scalar(select(func.count()).select_from(EvaluationResult)) == 0
    assert db.scalar(select(func.count()).select_from(EvidenceItem)) == 0


@pytest.mark.parametrize(
    ("schema", "mode", "stage", "expected_calls"),
    [
        (RequirementExtractionOutput, "permanent", "requirement_extraction", 1),  # not retried
        (RequirementExtractionOutput, "timeout", "requirement_extraction", 3),
        (CriterionEvaluationOutput, "malformed", "independent_evaluation", 3),
        (CriterionEvaluationOutput, "fake_evidence", "independent_evaluation", 3),
        (CriterionEvaluationOutput, "out_of_scale", "independent_evaluation", 3),
        (PairwiseComparisonOutput, "timeout", "pairwise_comparison", 3),
        (ComplianceCheckOutput, "malformed", "reward_mismatch", 3),
    ],
)
def test_failures_mark_run_failed(db, evaluation, schema, mode, stage, expected_calls):
    provider = FailingAt(schema, mode)
    run = _run(db, evaluation["id"], provider)
    _assert_failed_cleanly(db, run, stage)
    assert provider.calls == expected_calls
    assert len(run.raw_output["error"]["retried_errors"]) == expected_calls


def test_failure_keeps_partial_raw_output_for_debugging(db, evaluation):
    run = _run(db, evaluation["id"], FailingAt(PairwiseComparisonOutput, "timeout"))
    stages = run.raw_output["stages"]
    assert "requirement_extraction" in stages and "independent_evaluation" in stages
    assert "improvement" not in stages
    assert run.input_tokens and run.input_tokens > 0  # usage of completed calls is still recorded


def test_failed_run_via_api_then_retry_succeeds(client, evaluation, monkeypatch):
    eid = evaluation["id"]
    monkeypatch.setattr(
        evaluation_service, "get_llm_provider", lambda: FailingAt(RequirementExtractionOutput, "permanent")
    )
    r = client.post(f"/api/v1/evaluations/{eid}/run")
    assert r.status_code == 202
    run = client.get(f"/api/v1/evaluations/{eid}/runs/{r.json()['id']}").json()
    assert run["status"] == "FAILED" and "invalid api key" in run["error"]["message"]
    assert client.get(f"/api/v1/evaluations/{eid}").json()["status"] == "FAILED"
    assert client.get(f"/api/v1/evaluations/{eid}/report").status_code == 404

    monkeypatch.setattr(evaluation_service, "get_llm_provider", lambda: MockLLMProvider())
    retry = client.post(f"/api/v1/evaluations/{eid}/run")
    assert retry.status_code == 202
    assert client.get(f"/api/v1/evaluations/{eid}").json()["status"] == "COMPLETED"
    report = client.get(f"/api/v1/evaluations/{eid}/report").json()
    assert report["run"]["id"] == retry.json()["id"]
    runs = client.get(f"/api/v1/evaluations/{eid}/runs").json()
    assert [x["status"] for x in runs] == ["FAILED", "COMPLETED"]


def test_misconfigured_provider_returns_503_and_creates_no_run(client, evaluation, monkeypatch):
    from app.providers import ProviderConfigError

    def broken():
        raise ProviderConfigError("LLM_PROVIDER=openai_compatible requires LLM_API_KEY")

    monkeypatch.setattr(evaluation_service, "get_llm_provider", broken)
    r = client.post(f"/api/v1/evaluations/{evaluation['id']}/run")
    assert r.status_code == 503 and "LLM_API_KEY" in r.json()["detail"]
    assert client.get(f"/api/v1/evaluations/{evaluation['id']}/runs").json() == []
    assert client.get(f"/api/v1/evaluations/{evaluation['id']}").json()["status"] == "DRAFT"
