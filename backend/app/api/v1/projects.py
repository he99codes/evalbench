import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return project_service.list_projects(db)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    return project_service.create_project(db, data)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return project_service.get_project(db, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: uuid.UUID, data: ProjectUpdate, db: Session = Depends(get_db)):
    return project_service.update_project(db, project_id, data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    project_service.delete_project(db, project_id)
