"""Test setup: a dedicated Postgres database (<name>_test), migrated with Alembic.

Tests need real Postgres (JSONB, native enums), so run them in the container:
    docker compose exec backend pytest
"""

import os
from pathlib import Path

from sqlalchemy.engine import make_url

_base_url = make_url(
    os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://evalbench:evalbench@localhost:5432/evalbench"
    )
)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _base_url.set(
    database=f"{_base_url.database}_test"
).render_as_string(hide_password=False)

# Must happen before any `app` import: settings and the engine read DATABASE_URL.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = ""
os.environ["LLM_RETRY_BASE_DELAY_SECONDS"] = "0"  # no real sleeping in background runs
os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _ensure_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    assert url.database and url.database.endswith("_test"), "refusing to run tests on a non-test DB"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    _ensure_test_database()
    # No ini file -> env.py skips fileConfig, so pytest's logging stays intact.
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    # Every table hangs off projects via FK cascades.
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE projects CASCADE"))


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


API = "/api/v1"

DEFAULT_PROMPT = (
    "Write a reply to the customer. The reply must apologize for the delay and offer a "
    "discount code. Keep the reply under 50 words. Do not mention competitors."
)


class ApiHelper:
    """Small factory helpers that go through the real HTTP API."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def create_project(self, name: str = "Test project", **extra) -> dict:
        r = self.client.post(f"{API}/projects", json={"name": name, **extra})
        assert r.status_code == 201, r.text
        return r.json()

    def create_criterion(self, project_id: str, name: str = "Accuracy", **extra) -> dict:
        r = self.client.post(
            f"{API}/projects/{project_id}/criteria",
            json={"name": name, "description": f"{name} description", **extra},
        )
        assert r.status_code == 201, r.text
        return r.json()

    def evaluation_payload(self, project_id: str, criteria: list[dict], **extra) -> dict:
        return {
            "project_id": project_id,
            "title": "Delay reply",
            "prompt": DEFAULT_PROMPT,
            "response_a": "Sorry for the delay. Here is a discount code: SAVE10.",
            "response_b": "We apologize. Use code SAVE10 for a discount. Unlike CompetitorX, we care.",
            "criteria": [{"criterion_id": c["id"]} for c in criteria],
            **extra,
        }

    def create_evaluation(self, project_id: str, criteria: list[dict], **extra) -> dict:
        r = self.client.post(
            f"{API}/evaluations", json=self.evaluation_payload(project_id, criteria, **extra)
        )
        assert r.status_code == 201, r.text
        return r.json()

    def setup_evaluation(self, criteria_names=("Accuracy", "Clarity")) -> tuple[dict, list[dict], dict]:
        project = self.create_project()
        criteria = [self.create_criterion(project["id"], n) for n in criteria_names]
        return project, criteria, self.create_evaluation(project["id"], criteria)


@pytest.fixture
def api(client: TestClient) -> ApiHelper:
    return ApiHelper(client)
