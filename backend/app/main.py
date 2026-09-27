"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.database import check_database_connection
from app.core.logging import configure_logging
from app.providers import ProviderConfigError
from app.services import ServiceError

settings = get_settings()
configure_logging(settings.app_env)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Background runs live in-process; any left RUNNING by a restart are marked FAILED.
    from app.services.evaluation_service import recover_interrupted_runs

    try:
        recovered = recover_interrupted_runs()
        if recovered:
            logger.warning("Marked %d interrupted run(s) as FAILED", recovered)
    except SQLAlchemyError:
        logger.exception("Could not recover interrupted runs (database unavailable?)")
    yield


app = FastAPI(title="EvalBench API", version="0.1.0", lifespan=lifespan)

# Origins come from CORS_ORIGINS (comma-separated). No cookie/session auth in V1.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(ProviderConfigError)
async def provider_config_error_handler(_: Request, exc: ProviderConfigError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": f"LLM provider misconfigured: {exc}"})


@app.get("/health", tags=["health"])
def health() -> JSONResponse:
    """Liveness + database connectivity check.

    Returns 200 when the API and database are both reachable, 503 otherwise.
    Also reports the configured evaluator (never any credentials).
    """
    database_ok = check_database_connection()
    return JSONResponse(
        status_code=status.HTTP_200_OK if database_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ok" if database_ok else "degraded",
            "database": "ok" if database_ok else "unavailable",
            "app_env": settings.app_env,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.effective_llm_model,
        },
    )


app.include_router(api_router)
