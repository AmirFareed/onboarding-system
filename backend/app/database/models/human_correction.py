"""Human correction model.

Stores a field-level correction applied by a reviewer. Keeping the original
value alongside the corrected value preserves the audit trail of what the
system extracted versus what the reviewer confirmed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.human_review import HumanReview


class HumanCorrection(Base):
    """A single field corrected during a human review.

    Attributes:
        id: Auto-incrementing primary key.
        review_id: Review that produced the correction (foreign key, cascades).
        field_name: Name of the corrected field.
        document_id: Document the corrected field was extracted from, when
            known (``SET NULL`` on delete). Disambiguates a field name shared
            by two documents on the same application; may be null for
            corrections submitted before this column existed.
        original_value: Value extracted by the system before correction.
        corrected_value: Value confirmed by the reviewer.
        reason: Optional explanation for the correction.
    """

    __tablename__ = "human_corrections"
    __table_args__ = (
        Index("ix_human_corrections_review_id", "review_id"),
        Index("ix_human_corrections_document_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("human_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_value: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    review: Mapped[HumanReview] = relationship(back_populates="corrections")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<HumanCorrection id={self.id} field={self.field_name}>"
