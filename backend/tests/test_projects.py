import uuid

from conftest import API


def test_create_and_read_project(client, api):
    created = api.create_project("Support bot", description="Replies")
    assert created["name"] == "Support bot"
    assert set(created) == {"id", "name", "description", "created_at", "updated_at"}

    r = client.get(f"{API}/projects/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created

    listed = client.get(f"{API}/projects").json()
    assert [p["id"] for p in listed] == [created["id"]]


def test_update_project(client, api):
    project = api.create_project()
    r = client.patch(f"{API}/projects/{project['id']}", json={"name": "  Renamed  "})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["description"] is None

    r = client.patch(f"{API}/projects/{project['id']}", json={"description": "d"})
    assert r.json()["name"] == "Renamed" and r.json()["description"] == "d"


def test_delete_project_cascades(client, api):
    project, criteria, evaluation = api.setup_evaluation()
    assert client.delete(f"{API}/projects/{project['id']}").status_code == 204
    assert client.get(f"{API}/projects/{project['id']}").status_code == 404
    assert client.get(f"{API}/evaluations/{evaluation['id']}").status_code == 404


def test_project_validation(client):
    assert client.post(f"{API}/projects", json={"name": ""}).status_code == 422
    assert client.post(f"{API}/projects", json={"name": "   "}).status_code == 422
    assert client.post(f"{API}/projects", json={}).status_code == 422
    assert client.post(f"{API}/projects", json={"name": "x", "bogus": 1}).status_code == 422


def test_update_rejects_null_name(client, api):
    project = api.create_project()
    assert client.patch(f"{API}/projects/{project['id']}", json={"name": None}).status_code == 422


def test_missing_project_returns_404(client):
    missing = uuid.uuid4()
    assert client.get(f"{API}/projects/{missing}").status_code == 404
    assert client.patch(f"{API}/projects/{missing}", json={"name": "x"}).status_code == 404
    assert client.delete(f"{API}/projects/{missing}").status_code == 404
    assert client.get(f"{API}/projects/not-a-uuid").status_code == 422
