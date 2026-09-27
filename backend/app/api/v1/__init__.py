from fastapi import APIRouter

from app.api.v1 import criteria, evaluations, projects, reports

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(projects.router)
api_router.include_router(criteria.router)
api_router.include_router(evaluations.router)
api_router.include_router(reports.router)
