import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.report import AgreementRead, ProjectAnalytics, ReportRead
from app.services import report_service

router = APIRouter(tags=["reports"])


@router.get("/evaluations/{evaluation_id}/report", response_model=ReportRead)
def get_report(
    evaluation_id: uuid.UUID, run_id: uuid.UUID | None = None, db: Session = Depends(get_db)
):
    """Report for the latest completed run (or a specific `run_id`)."""
    return report_service.build_report(db, evaluation_id, run_id)


@router.get("/evaluations/{evaluation_id}/agreement", response_model=AgreementRead)
def evaluator_agreement(
    evaluation_id: uuid.UUID, run_1: uuid.UUID, run_2: uuid.UUID, db: Session = Depends(get_db)
):
    """Agreement between two completed runs (e.g. two providers or two rubric versions)."""
    return report_service.evaluator_agreement(db, evaluation_id, run_1, run_2)


@router.get("/projects/{project_id}/analytics", response_model=ProjectAnalytics)
def project_analytics(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Aggregate stats across the project's completed evaluations (latest run of each)."""
    return report_service.project_analytics(db, project_id)


@router.get("/evaluations/{evaluation_id}/export/json")
def export_json(evaluation_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(
        content=report_service.export_json(db, evaluation_id),
        headers={"Content-Disposition": f'attachment; filename="evaluation-{evaluation_id}.json"'},
    )
