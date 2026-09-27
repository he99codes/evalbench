import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, CreatedAtMixin
from app.models.evaluation import pg_enum
from app.models.result import ResponseLabel

if TYPE_CHECKING:
    from app.models.result import EvaluationResult


class EvidenceItem(CreatedAtMixin, Base):
    """A verbatim quote from a response backing one criterion score."""

    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evaluation_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    response: Mapped[ResponseLabel] = mapped_column(
        pg_enum(ResponseLabel, "response_label"), nullable=False
    )
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    # Character span in the response, computed by evidence_service (e.g. "chars 10-58").
    location: Mapped[str | None] = mapped_column(Text)
    # What the quote demonstrates for the criterion.
    supports: Mapped[str] = mapped_column(Text, nullable=False)

    result: Mapped["EvaluationResult"] = relationship(back_populates="evidence")
