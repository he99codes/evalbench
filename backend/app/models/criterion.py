import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, CreatedAtMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.evaluation import Evaluation
    from app.models.project import Project


class Criterion(TimestampMixin, Base):
    """A rubric criterion owned by a project. `weight` is the project default."""

    __tablename__ = "criteria"
    __table_args__ = (
        CheckConstraint("weight >= 0", name="ck_criteria_weight_non_negative"),
        CheckConstraint("scale_min < scale_max", name="ck_criteria_scale_range"),
        UniqueConstraint("project_id", "name", name="uq_criteria_project_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    scale_min: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scale_max: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    project: Mapped["Project"] = relationship(back_populates="criteria")


class EvaluationCriterion(CreatedAtMixin, Base):
    """Which criteria an evaluation uses, with the weight snapshotted per evaluation.

    Approved schema addition (Q1): lets one evaluation use a subset of project
    criteria and override weights without mutating the project's rubric.
    """

    __tablename__ = "evaluation_criteria"
    __table_args__ = (
        CheckConstraint("weight >= 0", name="ck_evaluation_criteria_weight_non_negative"),
        UniqueConstraint("evaluation_id", "criterion_id", name="uq_evaluation_criteria_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # CASCADE so project deletion can cascade cleanly. Deleting a criterion that
    # is in use is blocked in criterion_service (409), not by the FK.
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("criteria.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="criteria_links")
    criterion: Mapped["Criterion"] = relationship(lazy="joined")
