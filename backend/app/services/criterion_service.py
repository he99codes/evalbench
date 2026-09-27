import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Criterion, EvaluationCriterion, EvaluationResult
from app.schemas.criterion import CriterionCreate, CriterionUpdate
from app.services import ConflictError, InvalidRequestError, NotFoundError
from app.services.project_service import get_project


def list_criteria(db: Session, project_id: uuid.UUID) -> list[Criterion]:
    get_project(db, project_id)
    return list(
        db.scalars(
            select(Criterion).where(Criterion.project_id == project_id).order_by(Criterion.created_at)
        )
    )


def get_criterion(db: Session, criterion_id: uuid.UUID) -> Criterion:
    criterion = db.get(Criterion, criterion_id)
    if criterion is None:
        raise NotFoundError(f"Criterion {criterion_id} not found")
    return criterion


def _ensure_unique_name(
    db: Session, project_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
) -> None:
    query = select(Criterion.id).where(Criterion.project_id == project_id, Criterion.name == name)
    if exclude_id is not None:
        query = query.where(Criterion.id != exclude_id)
    if db.scalar(query) is not None:
        raise ConflictError(f"A criterion named '{name}' already exists in this project")


def create_criterion(db: Session, project_id: uuid.UUID, data: CriterionCreate) -> Criterion:
    get_project(db, project_id)
    _ensure_unique_name(db, project_id, data.name)
    criterion = Criterion(project_id=project_id, **data.model_dump())
    db.add(criterion)
    db.commit()
    return criterion


def update_criterion(db: Session, criterion_id: uuid.UUID, data: CriterionUpdate) -> Criterion:
    criterion = get_criterion(db, criterion_id)
    changes = data.model_dump(exclude_unset=True)

    scale_min = changes.get("scale_min", criterion.scale_min)
    scale_max = changes.get("scale_max", criterion.scale_max)
    if scale_min >= scale_max:
        raise InvalidRequestError("scale_min must be less than scale_max")
    if (scale_min, scale_max) != (criterion.scale_min, criterion.scale_max) and _has_results(
        db, criterion.id
    ):
        raise ConflictError(
            "Cannot change the scale of a criterion that already has scored results; "
            "create a new criterion instead"
        )
    if "name" in changes:
        _ensure_unique_name(db, criterion.project_id, changes["name"], exclude_id=criterion.id)

    for field, value in changes.items():
        setattr(criterion, field, value)
    db.commit()
    return criterion


def _has_results(db: Session, criterion_id: uuid.UUID) -> bool:
    return bool(db.scalar(select(exists().where(EvaluationResult.criterion_id == criterion_id))))


def delete_criterion(db: Session, criterion_id: uuid.UUID) -> None:
    criterion = get_criterion(db, criterion_id)
    in_use = db.scalar(
        select(exists().where(EvaluationCriterion.criterion_id == criterion_id))
    ) or _has_results(db, criterion_id)
    if in_use:
        raise ConflictError(
            "Criterion is used by one or more evaluations. Disable it instead "
            "(PATCH enabled=false) so existing evaluations and results stay intact."
        )
    db.delete(criterion)
    db.commit()
