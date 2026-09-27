import json
from pathlib import Path

from app.providers.mock_provider import MockLLMProvider
from app.services import evaluation_service

DEMO = json.loads((Path(__file__).resolve().parents[2] / "data" / "demo" / "refund_example.json").read_text())
API = "/api/v1"


def _complete(db, evaluation_id):
    provider = MockLLMProvider()
    run = evaluation_service.start_run(db, evaluation_id, provider=provider)
    evaluation_service.execute_run(run.id, provider, sleep=lambda s: None)


def test_analytics_empty_project(client, api):
    project = api.create_project()
    body = client.get(f"{API}/projects/{project['id']}/analytics").json()
    assert body["total_evaluations"] == 0 and body["completed_evaluations"] == 0
    assert body["preference"] == {"A": 0, "B": 0, "TIE": 0}
    assert body["average_quality"] is None and body["constraint_compliance_rate"] is None
    assert body["most_common_failing_criterion"] is None and body["criteria"] == []


def test_analytics_aggregates_completed_evaluations(client, api, db):
    project = api.create_project()
    criteria = [
        api.create_criterion(project["id"], c["name"], description=c["description"], weight=c["weight"])
        for c in DEMO["criteria"]
    ]
    e = DEMO["evaluation"]
    refund = api.create_evaluation(project["id"], criteria, prompt=e["prompt"], response_a=e["response_a"], response_b=e["response_b"])
    # Swapped responses -> A should now be preferred.
    swapped = api.create_evaluation(project["id"], criteria, prompt=e["prompt"], response_a=e["response_b"], response_b=e["response_a"])
    api.create_evaluation(project["id"], criteria)  # stays DRAFT, excluded from verdict stats
    _complete(db, refund["id"])
    _complete(db, swapped["id"])

    body = client.get(f"{API}/projects/{project['id']}/analytics").json()
    assert body["total_evaluations"] == 3 and body["completed_evaluations"] == 2
    assert body["preference"] == {"A": 1, "B": 1, "TIE": 0}

    reports = [client.get(f"{API}/evaluations/{x['id']}/report").json() for x in (refund, swapped)]
    all_scores = [r[k]["overall_score"] for r in reports for k in ("summary_a", "summary_b")]
    assert body["average_quality"] == round(sum(all_scores) / 4, 2)
    satisfied = sum(r[k]["mandatory_satisfied"] for r in reports for k in ("summary_a", "summary_b"))
    total = sum(r[k]["mandatory_total"] for r in reports for k in ("summary_a", "summary_b"))
    assert (body["mandatory_checks_satisfied"], body["mandatory_checks_total"]) == (satisfied, total) == (20, 24)
    assert body["constraint_compliance_rate"] == 83.33
    worst = body["most_common_failing_criterion"]
    assert worst["failed"] == max(c["failed"] for c in body["criteria"]) > 0
    assert sum(p["A"] + p["B"] + p["TIE"] for p in body["preference_over_time"]) == 2


def test_rerun_counts_only_latest_run(client, api, db):
    project, criteria, evaluation = api.setup_evaluation()
    _complete(db, evaluation["id"])
    _complete(db, evaluation["id"])
    body = client.get(f"{API}/projects/{project['id']}/analytics").json()
    assert body["completed_evaluations"] == 1
    assert sum(c["evaluated"] for c in body["criteria"]) == 2 * len(criteria)  # one run, A + B


def test_analytics_missing_project_404(client):
    assert client.get(f"{API}/projects/00000000-0000-0000-0000-000000000000/analytics").status_code == 404
