"""Evaluator agreement between two runs + run metadata completeness."""

import pytest

from app.providers.base import LLMResponse
from app.providers.mock_provider import MockLLMProvider
from app.services import evaluation_service
from app.utils.validation import CriterionEvaluationOutput, PairwiseComparisonOutput

API = "/api/v1"


def _run(db, evaluation_id, provider):
    run = evaluation_service.start_run(db, evaluation_id, provider=provider)
    evaluation_service.execute_run(run.id, provider, sleep=lambda s: None)
    return str(run.id)


class HarshMock(MockLLMProvider):
    """A second 'evaluator': scores Tone at the scale minimum and always prefers Candidate 1."""

    def __init__(self):
        super().__init__(model="harsh-mock")

    def generate_structured(self, prompt, schema, *, system=None):
        response = super().generate_structured(prompt, schema, system=system)
        if schema is CriterionEvaluationOutput and 'name="Tone"' in prompt:
            response.data.update(score=1, passed=False)
        if schema is PairwiseComparisonOutput:
            response.data.update(preferred="CANDIDATE_1")
        return LLMResponse(response.data, response.raw_text, response.input_tokens, response.output_tokens, 1)


@pytest.fixture
def evaluation(api):
    _, _, evaluation = api.setup_evaluation(criteria_names=("Accuracy", "Tone"))
    return evaluation


def test_identical_runs_fully_agree(client, db, evaluation):
    r1 = _run(db, evaluation["id"], MockLLMProvider())
    r2 = _run(db, evaluation["id"], MockLLMProvider())
    body = client.get(f"{API}/evaluations/{evaluation['id']}/agreement", params={"run_1": r1, "run_2": r2}).json()
    assert body["preference_agrees"] and body["same_rubric"] and body["same_evaluator"]
    assert body["overall_agreement"] == 100 and body["pass_fail_agreement"] == 100
    assert body["mean_abs_score_difference"] == 0
    assert len(body["criteria"]) == 4  # 2 criteria x 2 responses
    assert (body["run_1"]["run_number"], body["run_2"]["run_number"]) == (1, 2)


def test_disagreeing_evaluator_metrics(client, db, evaluation):
    r1 = _run(db, evaluation["id"], MockLLMProvider())
    r2 = _run(db, evaluation["id"], HarshMock())
    body = client.get(f"{API}/evaluations/{evaluation['id']}/agreement", params={"run_1": r1, "run_2": r2}).json()
    assert not body["same_evaluator"] and body["run_2"]["evaluator_model"] == "harsh-mock"
    tone = [c for c in body["criteria"] if c["name"] == "Tone"]
    accuracy = [c for c in body["criteria"] if c["name"] == "Accuracy"]
    assert all(c["score_2"] == 1 and not c["passed_2"] for c in tone)
    assert all(c["normalized_difference"] == 0 and c["pass_agrees"] for c in accuracy)
    # Recompute every headline metric from the per-criterion rows.
    rows = body["criteria"]
    matches = sum(c["pass_agrees"] for c in rows)
    assert body["pass_fail_agreement"] == round(100 * matches / len(rows), 2)
    assert body["mean_abs_score_difference"] == round(sum(c["normalized_difference"] for c in rows) / len(rows), 4)
    assert body["overall_agreement"] == round(100 * (matches + body["preference_agrees"]) / (len(rows) + 1), 2)
    assert body["overall_score_difference_a"] == round(body["run_2"]["overall_score_a"] - body["run_1"]["overall_score_a"], 2)


def test_different_rubric_versions_are_reported(client, db, api, evaluation):
    r1 = _run(db, evaluation["id"], MockLLMProvider())
    links = client.get(f"{API}/evaluations/{evaluation['id']}").json()["criteria"]
    client.patch(
        f"{API}/evaluations/{evaluation['id']}",
        json={"criteria": [{"criterion_id": links[0]["criterion_id"], "weight": 5}]},
    )
    r2 = _run(db, evaluation["id"], MockLLMProvider())
    body = client.get(f"{API}/evaluations/{evaluation['id']}/agreement", params={"run_1": r1, "run_2": r2}).json()
    assert not body["same_rubric"]
    assert body["criteria_only_in_one_run"] == [links[1]["criterion"]["name"]]
    assert len(body["criteria"]) == 2


def test_agreement_validation(client, db, evaluation, api):
    r1 = _run(db, evaluation["id"], MockLLMProvider())
    url = f"{API}/evaluations/{evaluation['id']}/agreement"
    assert client.get(url, params={"run_1": r1, "run_2": r1}).status_code == 422
    assert client.get(url, params={"run_1": r1}).status_code == 422
    assert client.get(url, params={"run_1": r1, "run_2": "00000000-0000-0000-0000-000000000000"}).status_code == 404
    _, _, other = api.setup_evaluation()
    other_run = _run(db, other["id"], MockLLMProvider())
    assert client.get(url, params={"run_1": r1, "run_2": other_run}).status_code == 404  # run of another evaluation


def test_every_run_records_full_metadata(client, db, evaluation):
    _run(db, evaluation["id"], MockLLMProvider())
    _run(db, evaluation["id"], HarshMock())
    runs = client.get(f"{API}/evaluations/{evaluation['id']}/runs").json()
    assert len(runs) == 2 and runs[0]["id"] != runs[1]["id"]
    for run in runs:
        for field in ("evaluator_model", "provider", "rubric_version", "prompt_version", "candidate_order"):
            assert run[field], field
        assert run["outcome"]["preferred_response"] in ("A", "B", "TIE")
        detail = client.get(f"{API}/evaluations/{evaluation['id']}/runs/{run['id']}").json()
        stages = detail["raw_output"]["stages"]
        assert set(stages) == {
            "requirement_extraction", "independent_evaluation", "pairwise_comparison", "improvement", "reward_mismatch",
        }
        assert all(call["raw_text"] for call in detail["raw_output"]["calls"])
    # Reports can be fetched per run.
    report_1 = client.get(f"{API}/evaluations/{evaluation['id']}/report", params={"run_id": runs[0]["id"]}).json()
    assert report_1["run"]["id"] == runs[0]["id"]
