"""Full pipeline with the MockLLMProvider only."""

import json
import random
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import (
    Evaluation,
    EvaluationResult,
    EvaluationRun,
    EvaluationStatus,
    EvidenceItem,
    RunStatus,
)
from app.providers.base import LLMResponse
from app.providers.mock_provider import MockLLMProvider
from app.services import evaluation_service
from app.utils import scoring
from app.utils.validation import CriterionEvaluationOutput

DEMO = json.loads(
    (Path(__file__).resolve().parents[2] / "data" / "demo" / "refund_example.json").read_text()
)
API = "/api/v1"


@pytest.fixture
def demo_evaluation(api):
    project = api.create_project("Demo")
    criteria = [
        api.create_criterion(project["id"], c["name"], description=c["description"], weight=c["weight"])
        for c in DEMO["criteria"]
    ]
    e = DEMO["evaluation"]
    return api.create_evaluation(
        project["id"], criteria, title=e["title"], prompt=e["prompt"],
        response_a=e["response_a"], response_b=e["response_b"],
    )


def _run(db, evaluation_id, provider=None, rng=None):
    provider = provider or MockLLMProvider()
    run = evaluation_service.start_run(db, evaluation_id, provider=provider)
    evaluation_service.execute_run(run.id, provider, rng=rng, sleep=lambda s: None)
    db.expire_all()
    return db.get(EvaluationRun, run.id)


def test_pipeline_completes_with_evidence_and_metadata(db, demo_evaluation):
    run = _run(db, demo_evaluation["id"])
    assert run.status == RunStatus.COMPLETED, run.raw_output.get("error")
    assert (run.evaluator_model, run.provider) == ("mock", "mock")
    assert run.rubric_version.startswith("sha256:") and run.prompt_version
    assert run.candidate_order in ("AB", "BA")
    assert run.input_tokens > 0 and run.output_tokens > 0 and run.latency_ms is not None
    assert set(run.raw_output["stages"]) == {
        "requirement_extraction", "independent_evaluation", "pairwise_comparison", "improvement", "reward_mismatch",
    }
    # 1 + 16 + 1 + 1 + 2 calls, all recorded.
    assert len(run.raw_output["calls"]) == 21
    assert run.raw_output["progress"]["completed_steps"] == run.raw_output["progress"]["total_steps"] == 21

    results = db.scalars(select(EvaluationResult).where(EvaluationResult.run_id == run.id)).all()
    assert len(results) == 16
    for result in results:
        assert result.evidence, "every criterion score must have evidence"
        text = demo_evaluation["response_a"] if result.response.value == "A" else demo_evaluation["response_b"]
        for item in result.evidence:
            assert item.quote in text  # verbatim
            start, end = map(int, item.location.removeprefix("chars ").split("-"))
            assert text[start:end] == item.quote


def test_overall_scores_are_deterministic_from_stored_results(db, demo_evaluation):
    run = _run(db, demo_evaluation["id"])
    evaluation = db.get(Evaluation, run.evaluation_id)
    snapshot = run.raw_output["criteria_snapshot"]
    weights = [scoring.CriterionWeight(c["criterion_id"], c["weight"], c["scale_min"], c["scale_max"]) for c in snapshot]
    for label, stored in (("A", evaluation.overall_score_a), ("B", evaluation.overall_score_b)):
        rows = db.scalars(
            select(EvaluationResult).where(EvaluationResult.run_id == run.id, EvaluationResult.response == label)
        ).all()
        recomputed = scoring.aggregate_score(weights, {str(r.criterion_id): r.score for r in rows})
        assert stored == recomputed
    assert evaluation.status == EvaluationStatus.COMPLETED
    assert evaluation.preferred_response.value == "B"  # B satisfies every mandatory requirement
    assert evaluation.final_reasoning and evaluation.improvement


def test_same_input_same_output(db, demo_evaluation):
    first = _run(db, demo_evaluation["id"], rng=random.Random(1))
    second = _run(db, demo_evaluation["id"], rng=random.Random(1))
    assert first.raw_output["scores"] == second.raw_output["scores"]
    assert first.candidate_order == second.candidate_order
    assert db.scalar(select(func.count()).select_from(EvaluationRun)) == 2
    # Each run keeps its own results; the second did not overwrite the first.
    assert db.scalar(select(func.count()).select_from(EvaluationResult)) == 32


def test_independent_scoring_never_sees_other_response(db, demo_evaluation):
    seen = []

    class Spy(MockLLMProvider):
        def generate_structured(self, prompt, schema, *, system=None):
            if schema is CriterionEvaluationOutput:
                seen.append(prompt)
            return super().generate_structured(prompt, schema, system=system)

    _run(db, demo_evaluation["id"], provider=Spy())
    assert len(seen) == 16
    a, b = demo_evaluation["response_a"], demo_evaluation["response_b"]
    for prompt in seen:
        assert (a in prompt) != (b in prompt)


def test_candidate_order_is_mapped_back_to_a_b(db, demo_evaluation):
    orders = {}
    for seed in range(20):
        run = _run(db, demo_evaluation["id"], rng=random.Random(seed))
        orders.setdefault(run.candidate_order, run)
        if len(orders) == 2:
            break
    assert set(orders) == {"AB", "BA"}
    # The mock is position-independent, so the mapped preference must be identical.
    prefs = {o: r.raw_output["stages"]["pairwise_comparison"]["preferred_response"] for o, r in orders.items()}
    assert prefs["AB"] == prefs["BA"] == "B"


def test_run_endpoint_and_report(client, demo_evaluation):
    eid = demo_evaluation["id"]
    assert client.get(f"{API}/evaluations/{eid}/report").status_code == 404
    r = client.post(f"{API}/evaluations/{eid}/run")
    assert r.status_code == 202, r.text
    run_id = r.json()["id"]
    # TestClient executes background tasks before returning.
    run = client.get(f"{API}/evaluations/{eid}/runs/{run_id}").json()
    assert run["status"] == "COMPLETED" and run["error"] is None
    assert run["progress"]["completed_steps"] == run["progress"]["total_steps"]
    assert "stages" in run["raw_output"]
    assert [x["id"] for x in client.get(f"{API}/evaluations/{eid}/runs").json()] == [run_id]

    report = client.get(f"{API}/evaluations/{eid}/report").json()
    assert report["run"]["id"] == run_id
    assert len(report["criteria"]) == 8 and len(report["requirements"]) == 7
    assert report["preference"]["preferred_response"] == "B"
    assert report["improvement"]["target_response"] in ("A", "B")
    assert report["summary_a"]["compliance_rate"] == 66.67 and report["summary_b"]["compliance_rate"] == 100
    assert all(row["a"]["evidence"] and row["b"]["evidence"] for row in report["criteria"])
    assert report["evidence_a"] and report["evidence_b"]

    exported = client.get(f"{API}/evaluations/{eid}/export/json")
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    assert exported.json()["run_raw_output"]["stages"]


def test_cannot_start_second_run_while_running(db, demo_evaluation):
    run = evaluation_service.start_run(db, demo_evaluation["id"], provider=MockLLMProvider())
    from app.services import ConflictError

    with pytest.raises(ConflictError):
        evaluation_service.start_run(db, demo_evaluation["id"], provider=MockLLMProvider())
    evaluation_service.execute_run(run.id, MockLLMProvider(), sleep=lambda s: None)


def test_recover_interrupted_runs(db, demo_evaluation):
    run = evaluation_service.start_run(db, demo_evaluation["id"], provider=MockLLMProvider())
    assert evaluation_service.recover_interrupted_runs() == 1
    db.expire_all()
    run = db.get(EvaluationRun, run.id)
    assert run.status == RunStatus.FAILED and run.raw_output["error"]["type"] == "Interrupted"
    assert db.get(Evaluation, run.evaluation_id).status == EvaluationStatus.FAILED


def test_duplicate_evidence_is_stored_once(db, demo_evaluation):
    sentence = "The duplicate charge will be refunded to your original payment method."

    class DuplicateEvidence(MockLLMProvider):
        def generate_structured(self, prompt, schema, *, system=None):
            response = super().generate_structured(prompt, schema, system=system)
            if schema is CriterionEvaluationOutput and sentence in prompt:
                response.data["evidence"] = [
                    {"quote": sentence, "supports": "one"},
                    {"quote": f'"{sentence}"', "supports": "same quote, wrapped"},
                    {"quote": "  " + sentence.replace(" ", "  "), "supports": "same quote, spacing"},
                    {"quote": "duplicate charge will be refunded", "supports": "contained fragment"},
                ]
            return response

    run = _run(db, demo_evaluation["id"], provider=DuplicateEvidence())
    assert run.status == RunStatus.COMPLETED
    b_results = db.scalars(
        select(EvaluationResult).where(EvaluationResult.run_id == run.id, EvaluationResult.response == "B")
    ).all()
    for result in b_results:
        assert [e.quote for e in result.evidence] == [sentence]
    assert db.scalar(select(func.count()).select_from(EvidenceItem)) >= 16


def test_anonymize_reasoning_handles_real_world_variants():
    """Regression: a live Groq run produced 'Candidate\u202f2' (non-breaking space),
    'Candidateâ¯1', and lowercase/underscore forms that exact-string .replace() missed,
    leaking the anonymized label into what the UI shows the user."""
    from app.services.comparison_service import anonymize_reasoning

    cases = [
        "Candidate\u202f2 scores higher than Candidate\u202f1 overall.",
        "candidate 1 fails Constraint Compliance; CANDIDATE_2 passes it.",
        "Candidate#1 and candidate_2 are close on Tone.",
    ]
    for reasoning in cases:
        result = anonymize_reasoning(reasoning, first="A", second="B")
        assert "andidate" not in result.lower()
        assert "Response A" in result and "Response B" in result
