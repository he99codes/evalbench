"""Database engine, session factory and declarative base.

Alembic's env.py imports `Base` from here so migrations and the application
always share one configuration source.
"""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # Fail fast on health checks instead of hanging when the DB is unreachable.
    connect_args={"connect_timeout": 3},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""


class CreatedAtMixin:
    # Python-side default keeps the value available without a refresh;
    # server_default keeps raw SQL inserts consistent.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> bool:
    """Return True if a trivial query succeeds against the configured database."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        logger.exception("Database connectivity check failed")
        return False
