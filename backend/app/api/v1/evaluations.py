import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import EvaluationStatus
from app.schemas.evaluation import (
    AnalyzePromptResponse,
    EvaluationCreate,
    EvaluationRead,
    EvaluationRunDetail,
    EvaluationRunRead,
    EvaluationSummary,
    EvaluationUpdate,
)
from app.services import evaluation_service, requirement_service

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("", response_model=list[EvaluationSummary])
def list_evaluations(
    project_id: uuid.UUID | None = None,
    status: EvaluationStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return evaluation_service.list_evaluations(
        db, project_id=project_id, status=status, limit=limit, offset=offset
    )


@router.post("", response_model=EvaluationRead, status_code=status.HTTP_201_CREATED)
def create_evaluation(data: EvaluationCreate, db: Session = Depends(get_db)):
    return evaluation_service.create_evaluation(db, data)


@router.get("/{evaluation_id}", response_model=EvaluationRead)
def get_evaluation(evaluation_id: uuid.UUID, db: Session = Depends(get_db)):
    return evaluation_service.get_evaluation(db, evaluation_id)


@router.patch("/{evaluation_id}", response_model=EvaluationRead)
def update_evaluation(
    evaluation_id: uuid.UUID, data: EvaluationUpdate, db: Session = Depends(get_db)
):
    return evaluation_service.update_evaluation(db, evaluation_id, data)


@router.delete("/{evaluation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evaluation(evaluation_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    evaluation_service.delete_evaluation(db, evaluation_id)


@router.post("/{evaluation_id}/analyze-prompt", response_model=AnalyzePromptResponse)
def analyze_prompt(evaluation_id: uuid.UUID, db: Session = Depends(get_db)):
    """Stage 1 only: extract requirements from the prompt (DRAFT -> READY)."""
    return requirement_service.analyze_prompt(db, evaluation_id)


@router.post(
    "/{evaluation_id}/run", response_model=EvaluationRunRead, status_code=status.HTTP_202_ACCEPTED
)
def run_evaluation(
    evaluation_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Start the 5-stage pipeline in the background. Poll GET /runs/{run_id} for progress."""
    return evaluation_service.start_run(db, evaluation_id, schedule=background_tasks.add_task)


@router.get("/{evaluation_id}/runs", response_model=list[EvaluationRunRead])
def list_runs(evaluation_id: uuid.UUID, db: Session = Depends(get_db)):
    return evaluation_service.list_runs(db, evaluation_id)


@router.get("/{evaluation_id}/runs/{run_id}", response_model=EvaluationRunDetail)
def get_run(evaluation_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db)):
    """Run status, progress, error (if any) and the full raw_output for auditing."""
    return evaluation_service.get_run(db, evaluation_id, run_id)
