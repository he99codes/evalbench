import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, CreatedAtMixin
from app.models.evaluation import pg_enum

if TYPE_CHECKING:
    from app.models.criterion import Criterion
    from app.models.evaluation import Evaluation
    from app.models.evidence import EvidenceItem
    from app.models.run import EvaluationRun


class ResponseLabel(enum.StrEnum):
    A = "A"
    B = "B"


class EvaluationResult(CreatedAtMixin, Base):
    """One criterion score for one response within one run."""

    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "criterion_id", "response", name="uq_evaluation_results_run_criterion"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Approved schema addition (Q1): results are scoped to the run that produced them.
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # See EvaluationCriterion.criterion_id: in-use deletion is blocked in the service.
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("criteria.id", ondelete="CASCADE"), nullable=False, index=True
    )
    response: Mapped[ResponseLabel] = mapped_column(
        pg_enum(ResponseLabel, "response_label"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="results")
    run: Mapped["EvaluationRun"] = relationship(back_populates="results")
    criterion: Mapped["Criterion"] = relationship()
    evidence: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="result",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EvidenceItem.created_at",
    )
