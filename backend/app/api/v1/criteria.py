import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.criterion import CriterionCreate, CriterionRead, CriterionUpdate
from app.services import criterion_service

router = APIRouter(tags=["criteria"])


@router.get("/projects/{project_id}/criteria", response_model=list[CriterionRead])
def list_criteria(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return criterion_service.list_criteria(db, project_id)


@router.post(
    "/projects/{project_id}/criteria",
    response_model=CriterionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_criterion(project_id: uuid.UUID, data: CriterionCreate, db: Session = Depends(get_db)):
    return criterion_service.create_criterion(db, project_id, data)


@router.patch("/criteria/{criterion_id}", response_model=CriterionRead)
def update_criterion(criterion_id: uuid.UUID, data: CriterionUpdate, db: Session = Depends(get_db)):
    return criterion_service.update_criterion(db, criterion_id, data)


@router.delete("/criteria/{criterion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_criterion(criterion_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    criterion_service.delete_criterion(db, criterion_id)
