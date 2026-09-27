"""Phase 2: seeded rows validate through the Pydantic Read schemas."""

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models import Criterion, Evaluation, EvaluationStatus, Project
from app.schemas.criterion import CriterionCreate, CriterionRead
from app.schemas.evaluation import EvaluationCreate, EvaluationRead, EvaluationSummary
from app.schemas.project import ProjectRead

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "demo" / "seed.py"


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("demo_seed", SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seeded(db):
    seed = _load_seed_module()
    return seed.seed_demo(db)


def test_seed_creates_demo_data(db, seeded):
    assert db.scalar(select(func.count()).select_from(Project)) == 1
    names = db.scalars(select(Criterion.name).order_by(Criterion.created_at)).all()
    assert names == [
        "Instruction Following",
        "Constraint Compliance",
        "Accuracy",
        "Relevance",
        "Clarity",
        "Completeness",
        "Conciseness",
        "Tone",
    ]
    evaluation = db.scalar(select(Evaluation))
    assert evaluation.status == EvaluationStatus.DRAFT
    assert len(evaluation.criteria_links) == 8


def test_seed_is_idempotent(db, seeded):
    seed = _load_seed_module()
    seed.seed_demo(db)
    assert db.scalar(select(func.count()).select_from(Project)) == 1
    seed.seed_demo(db, reset=True)
    assert db.scalar(select(func.count()).select_from(Project)) == 1
    assert db.scalar(select(func.count()).select_from(Criterion)) == 8


def test_seeded_rows_validate_through_read_schemas(db, seeded):
    project = ProjectRead.model_validate(seeded)
    assert project.name.startswith("Demo")

    for criterion in seeded.criteria:
        read = CriterionRead.model_validate(criterion)
        assert read.scale_min < read.scale_max

    evaluation = db.scalar(select(Evaluation))
    read = EvaluationRead.model_validate(evaluation)
    assert read.status == EvaluationStatus.DRAFT
    assert len(read.criteria) == 8
    assert {c.criterion.name for c in read.criteria} >= {"Accuracy", "Tone"}
    assert read.requirements == []
    EvaluationSummary.model_validate(evaluation)


def test_read_schemas_are_not_orm_models():
    from app.core.database import Base

    for schema in (ProjectRead, CriterionRead, EvaluationRead):
        assert not issubclass(schema, Base)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "  "},
        {"name": "X", "weight": -1},
        {"name": "X", "scale_min": 5, "scale_max": 5},
        {"name": "X", "weight": float("nan")},
    ],
)
def test_criterion_create_rejects_invalid(payload):
    with pytest.raises(ValidationError):
        CriterionCreate.model_validate(payload)


def test_evaluation_create_rejects_blank_text():
    base = {
        "project_id": "00000000-0000-0000-0000-000000000001",
        "title": "t",
        "prompt": "p",
        "response_a": "a",
        "response_b": "b",
        "criteria": [{"criterion_id": "00000000-0000-0000-0000-000000000002"}],
    }
    EvaluationCreate.model_validate(base)
    for field in ("prompt", "response_a", "response_b", "title"):
        with pytest.raises(ValidationError):
            EvaluationCreate.model_validate({**base, field: " \n\t "})
