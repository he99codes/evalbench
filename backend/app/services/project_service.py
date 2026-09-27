import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import NotFoundError


def list_projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at)))


def get_project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    return project


def create_project(db: Session, data: ProjectCreate) -> Project:
    project = Project(**data.model_dump())
    db.add(project)
    db.commit()
    return project


def update_project(db: Session, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
    project = get_project(db, project_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    return project


def delete_project(db: Session, project_id: uuid.UUID) -> None:
    """Deletes the project and (via FK cascade) its criteria, evaluations and runs."""
    from app.services.evaluation_service import ensure_no_running_evaluations

    project = get_project(db, project_id)
    ensure_no_running_evaluations(db, project_id=project.id)
    db.delete(project)
    db.commit()
