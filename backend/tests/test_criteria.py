import uuid

import pytest

from conftest import API


def test_create_list_update_delete_criterion(client, api):
    project = api.create_project()
    created = api.create_criterion(project["id"], "Tone", weight=2, scale_min=0, scale_max=10)
    assert created["weight"] == 2 and created["scale_max"] == 10 and created["enabled"] is True

    listed = client.get(f"{API}/projects/{project['id']}/criteria").json()
    assert [c["id"] for c in listed] == [created["id"]]

    r = client.patch(f"{API}/criteria/{created['id']}", json={"weight": 0.5, "enabled": False})
    assert r.status_code == 200
    assert r.json()["weight"] == 0.5 and r.json()["enabled"] is False

    assert client.delete(f"{API}/criteria/{created['id']}").status_code == 204
    assert client.get(f"{API}/projects/{project['id']}/criteria").json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "X", "weight": -1},
        {"name": "X", "weight": 1000},
        {"name": "X", "scale_min": 5, "scale_max": 1},
        {"name": "X", "scale_min": 3, "scale_max": 3},
        {"name": ""},
    ],
)
def test_invalid_criteria_rejected(client, api, payload):
    project = api.create_project()
    r = client.post(f"{API}/projects/{project['id']}/criteria", json=payload)
    assert r.status_code == 422


def test_update_rejects_negative_weight_and_bad_merged_scale(client, api):
    project = api.create_project()
    c = api.create_criterion(project["id"], scale_min=1, scale_max=5)
    assert client.patch(f"{API}/criteria/{c['id']}", json={"weight": -0.1}).status_code == 422
    # Only scale_min sent, but merged with the stored scale_max it becomes invalid.
    assert client.patch(f"{API}/criteria/{c['id']}", json={"scale_min": 7}).status_code == 422
    assert client.patch(f"{API}/criteria/{c['id']}", json={"weight": None}).status_code == 422


def test_duplicate_name_conflicts(client, api):
    project = api.create_project()
    api.create_criterion(project["id"], "Accuracy")
    r = client.post(f"{API}/projects/{project['id']}/criteria", json={"name": "Accuracy"})
    assert r.status_code == 409
    other = api.create_criterion(project["id"], "Clarity")
    r = client.patch(f"{API}/criteria/{other['id']}", json={"name": "Accuracy"})
    assert r.status_code == 409


def test_criterion_in_use_cannot_be_deleted(client, api):
    project, criteria, _ = api.setup_evaluation()
    r = client.delete(f"{API}/criteria/{criteria[0]['id']}")
    assert r.status_code == 409
    assert "Disable it instead" in r.json()["detail"]
    # Disabling is the supported path.
    r = client.patch(f"{API}/criteria/{criteria[0]['id']}", json={"enabled": False})
    assert r.status_code == 200


def test_criteria_for_missing_project_404(client):
    missing = uuid.uuid4()
    assert client.get(f"{API}/projects/{missing}/criteria").status_code == 404
    assert client.post(f"{API}/projects/{missing}/criteria", json={"name": "x"}).status_code == 404
    assert client.patch(f"{API}/criteria/{missing}", json={"weight": 1}).status_code == 404


def test_changing_scale_after_scoring_is_blocked(client, db, api):
    from app.providers.mock_provider import MockLLMProvider
    from app.services import evaluation_service

    project, criteria, evaluation = api.setup_evaluation()
    provider = MockLLMProvider()
    run = evaluation_service.start_run(db, evaluation["id"], provider=provider)
    evaluation_service.execute_run(run.id, provider, sleep=lambda s: None)

    r = client.patch(f"{API}/criteria/{criteria[0]['id']}", json={"scale_max": 10})
    assert r.status_code == 409
    # Weight/description changes (not touching the scale) remain fine.
    assert client.patch(f"{API}/criteria/{criteria[0]['id']}", json={"weight": 3}).status_code == 200
