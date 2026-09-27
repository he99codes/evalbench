import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, CreatedAtMixin
from app.models.evaluation import pg_enum

if TYPE_CHECKING:
    from app.models.evaluation import Evaluation
    from app.models.result import EvaluationResult


class RunStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvaluationRun(CreatedAtMixin, Base):
    """Reproducibility record for one execution of the pipeline."""

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            "candidate_order IS NULL OR candidate_order IN ('AB', 'BA')",
            name="ck_evaluation_runs_candidate_order",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluator_model: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, "run_status"), nullable=False, default=RunStatus.PENDING
    )
    # Per-stage raw LLM outputs, criteria snapshot, progress and error details.
    raw_output: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    # "AB": Candidate 1 = A. "BA": Candidate 1 = B. Used for position-bias analysis.
    candidate_order: Mapped[str | None] = mapped_column(String(2))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    evaluation: Mapped["Evaluation"] = relationship(back_populates="runs")
    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
