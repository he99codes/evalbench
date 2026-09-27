import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, CreatedAtMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.criterion import EvaluationCriterion
    from app.models.project import Project
    from app.models.result import EvaluationResult
    from app.models.run import EvaluationRun


class EvaluationStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PreferredResponse(enum.StrEnum):
    A = "A"
    B = "B"
    TIE = "TIE"


class RequirementType(enum.StrEnum):
    REQUEST = "REQUEST"
    CONSTRAINT = "CONSTRAINT"
    FORMAT = "FORMAT"
    AUDIENCE = "AUDIENCE"
    LENGTH = "LENGTH"
    OTHER = "OTHER"


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Native PostgreSQL enum storing the member values."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Evaluation(TimestampMixin, Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response_a: Mapped[str] = mapped_column(Text, nullable=False)
    response_b: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(
        pg_enum(EvaluationStatus, "evaluation_status"),
        nullable=False,
        default=EvaluationStatus.DRAFT,
    )
    preferred_response: Mapped[PreferredResponse | None] = mapped_column(
        pg_enum(PreferredResponse, "preferred_response")
    )
    final_reasoning: Mapped[str | None] = mapped_column(Text)
    improvement: Mapped[str | None] = mapped_column(Text)
    # 0-100, computed deterministically by utils/scoring.py (never LLM-reported).
    overall_score_a: Mapped[float | None] = mapped_column(Float)
    overall_score_b: Mapped[float | None] = mapped_column(Float)

    project: Mapped["Project"] = relationship(back_populates="evaluations")
    requirements: Mapped[list["PromptRequirement"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PromptRequirement.created_at",
    )
    criteria_links: Mapped[list["EvaluationCriterion"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EvaluationCriterion.created_at",
    )
    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan", passive_deletes=True
    )
    runs: Mapped[list["EvaluationRun"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EvaluationRun.created_at",
    )


class PromptRequirement(CreatedAtMixin, Base):
    __tablename__ = "prompt_requirements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[RequirementType] = mapped_column(
        pg_enum(RequirementType, "requirement_type"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_text: Mapped[str | None] = mapped_column(Text)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="requirements")
