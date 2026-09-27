import uuid

import pytest

from conftest import API


def test_create_draft_evaluation_snapshots_weights(client, api):
    project = api.create_project()
    accuracy = api.create_criterion(project["id"], "Accuracy", weight=2)
    clarity = api.create_criterion(project["id"], "Clarity", weight=1)
    payload = api.evaluation_payload(project["id"], [accuracy, clarity])
    payload["criteria"][1]["weight"] = 3  # per-evaluation override

    r = client.post(f"{API}/evaluations", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "DRAFT"
    assert body["preferred_response"] is None and body["overall_score_a"] is None
    assert body["requirements"] == []
    weights = {c["criterion"]["name"]: c["weight"] for c in body["criteria"]}
    assert weights == {"Accuracy": 2, "Clarity": 3}

    # Changing the project default later does not change the evaluation's snapshot.
    client.patch(f"{API}/criteria/{accuracy['id']}", json={"weight": 5})
    fetched = client.get(f"{API}/evaluations/{body['id']}").json()
    assert {c["criterion"]["name"]: c["weight"] for c in fetched["criteria"]}["Accuracy"] == 2


def test_list_and_filter_evaluations(client, api):
    project, criteria, evaluation = api.setup_evaluation()
    other = api.create_project("Other")
    other_c = api.create_criterion(other["id"])
    api.create_evaluation(other["id"], [other_c])

    assert len(client.get(f"{API}/evaluations").json()) == 2
    scoped = client.get(f"{API}/evaluations", params={"project_id": project["id"]}).json()
    assert [e["id"] for e in scoped] == [evaluation["id"]]
    assert set(scoped[0]) == {
        "id", "project_id", "title", "status", "preferred_response",
        "overall_score_a", "overall_score_b", "created_at", "updated_at",
    }
    drafts = client.get(f"{API}/evaluations", params={"status": "DRAFT"}).json()
    assert len(drafts) == 2
    assert client.get(f"{API}/evaluations", params={"status": "NOPE"}).status_code == 422


def test_update_evaluation(client, api):
    project, criteria, evaluation = api.setup_evaluation()
    r = client.patch(f"{API}/evaluations/{evaluation['id']}", json={"title": "New title"})
    assert r.status_code == 200 and r.json()["title"] == "New title"

    r = client.patch(
        f"{API}/evaluations/{evaluation['id']}",
        json={"criteria": [{"criterion_id": criteria[1]["id"], "weight": 4}]},
    )
    assert r.status_code == 200
    assert [(c["criterion_id"], c["weight"]) for c in r.json()["criteria"]] == [
        (criteria[1]["id"], 4)
    ]
    assert r.json()["status"] == "DRAFT"


def test_delete_evaluation(client, api):
    _, _, evaluation = api.setup_evaluation()
    assert client.delete(f"{API}/evaluations/{evaluation['id']}").status_code == 204
    assert client.get(f"{API}/evaluations/{evaluation['id']}").status_code == 404
    assert client.delete(f"{API}/evaluations/{evaluation['id']}").status_code == 404


@pytest.mark.parametrize("field", ["prompt", "response_a", "response_b", "title"])
@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_rejects_empty_text(client, api, field, value):
    project = api.create_project()
    c = api.create_criterion(project["id"])
    payload = api.evaluation_payload(project["id"], [c], **{field: value})
    assert client.post(f"{API}/evaluations", json=payload).status_code == 422


def test_rejects_empty_text_on_update(client, api):
    _, _, evaluation = api.setup_evaluation()
    r = client.patch(f"{API}/evaluations/{evaluation['id']}", json={"response_a": "  "})
    assert r.status_code == 422


def test_rejects_invalid_weight_sets(client, api):
    project = api.create_project()
    a = api.create_criterion(project["id"], "A")
    b = api.create_criterion(project["id"], "B")

    def post(criteria):
        payload = api.evaluation_payload(project["id"], [a])
        payload["criteria"] = criteria
        return client.post(f"{API}/evaluations", json=payload)

    assert post([{"criterion_id": a["id"], "weight": -1}]).status_code == 422
    assert post([{"criterion_id": a["id"], "weight": 0}, {"criterion_id": b["id"], "weight": 0}]).status_code == 422
    assert post([{"criterion_id": a["id"]}, {"criterion_id": a["id"]}]).status_code == 422
    assert post([]).status_code == 422
    # Omitted weights fall back to project defaults; all-zero defaults are rejected too.
    client.patch(f"{API}/criteria/{a['id']}", json={"weight": 0})
    assert post([{"criterion_id": a["id"]}]).status_code == 422
    assert post([{"criterion_id": a["id"], "weight": 0}, {"criterion_id": b["id"], "weight": 1}]).status_code == 201


def test_rejects_foreign_disabled_or_missing_criteria(client, api):
    project = api.create_project()
    other = api.create_project("Other")
    foreign = api.create_criterion(other["id"], "Foreign")
    disabled = api.create_criterion(project["id"], "Disabled", enabled=False)

    r = client.post(f"{API}/evaluations", json=api.evaluation_payload(project["id"], [foreign]))
    assert r.status_code == 422 and "not found in this project" in r.json()["detail"]
    r = client.post(f"{API}/evaluations", json=api.evaluation_payload(project["id"], [disabled]))
    assert r.status_code == 422 and "Disabled" in r.json()["detail"]
    r = client.post(
        f"{API}/evaluations",
        json=api.evaluation_payload(str(uuid.uuid4()), [foreign]),
    )
    assert r.status_code == 404


def test_curl_style_end_to_end_flow(client):
    """Create project -> add criteria -> create draft evaluation -> fetch -> delete."""
    project = client.post(f"{API}/projects", json={"name": "E2E"}).json()
    crit = client.post(
        f"{API}/projects/{project['id']}/criteria", json={"name": "Accuracy", "weight": 1}
    ).json()
    evaluation = client.post(
        f"{API}/evaluations",
        json={
            "project_id": project["id"],
            "title": "t",
            "prompt": "Say hi.",
            "response_a": "Hi.",
            "response_b": "Hello.",
            "criteria": [{"criterion_id": crit["id"], "weight": 1}],
        },
    ).json()
    fetched = client.get(f"{API}/evaluations/{evaluation['id']}").json()
    assert fetched["status"] == "DRAFT" and fetched["criteria"][0]["criterion"]["name"] == "Accuracy"
    assert client.delete(f"{API}/evaluations/{evaluation['id']}").status_code == 204


def test_empty_response_text_is_rejected_and_run_requires_content(client, api):
    """Empty prompt/response text is rejected at creation, so the pipeline never sees it."""
    project = api.create_project()
    c = api.create_criterion(project["id"])
    for field in ("prompt", "response_a", "response_b"):
        payload = api.evaluation_payload(project["id"], [c])
        payload[field] = ""
        assert client.post(f"{API}/evaluations", json=payload).status_code == 422
    # Whitespace-only after a successful create (via update) is rejected the same way.
    evaluation = api.create_evaluation(project["id"], [c])
    assert client.patch(f"{API}/evaluations/{evaluation['id']}", json={"response_b": "\n \t"}).status_code == 422
