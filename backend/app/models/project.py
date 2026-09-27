import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.criterion import Criterion
    from app.models.evaluation import Evaluation


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Deleting a project deletes its criteria and evaluations (DB-level ON DELETE CASCADE).
    criteria: Mapped[list["Criterion"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Criterion.created_at",
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Evaluation.created_at",
    )
