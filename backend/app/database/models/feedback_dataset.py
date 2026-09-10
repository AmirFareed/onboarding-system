"""Feedback dataset model.

Collects field-level ground-truth pairs (OCR value vs. human-corrected value)
for future model improvement. Rows are retained indefinitely for dataset
building; nothing in this table triggers automatic retraining. The application
foreign key uses ``SET NULL`` so training data is preserved even when the source
application is removed.

The additive nullable columns (document, OCR result, normalized value,
confidence source, correction reason, reviewer, decision and origin) are
enriched by the confidence scoring and final human verification phases at write
time so the feedback module can read, aggregate and export a complete,
unambiguous dataset without re-running any pipeline stage.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.document import Document
    from app.database.models.ocr_result import OCRResult


class FeedbackEntry(Base):
    """A field-level OCR-versus-human sample for future training.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Source application (``SET NULL`` on delete).
        document_id: Document the corrected field was extracted from.
        ocr_result_id: OCR result the corrected field belongs to.
        field_name: Name of the field the sample describes.
        ocr_value: Value extracted by the OCR pipeline.
        normalized_value: Canonical form of the value, if normalization ran.
        human_value: Value confirmed/corrected by a human reviewer.
        confidence_score: Confidence the OCR pipeline assigned (0.0 - 1.0).
        confidence_source: Source that produced the confidence score.
        correction_reason: Optional explanation for the correction.
        reviewer: Name of the reviewer who corrected the field.
        decision: Review decision that produced the correction.
        origin: Whether the correction came from a low-confidence review or
            the final human review.
        recorded_at: When the sample was recorded (UTC).
    """

    __tablename__ = "feedback_dataset"
    __table_args__ = (
        Index("ix_feedback_dataset_application_id", "application_id"),
        Index("ix_feedback_dataset_document_id", "document_id"),
        Index("ix_feedback_dataset_field_name", "field_name"),
        Index("ix_feedback_dataset_reviewer", "reviewer"),
        Index("ix_feedback_dataset_decision", "decision"),
        Index("ix_feedback_dataset_origin", "origin"),
        Index("ix_feedback_dataset_recorded_at", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    ocr_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("ocr_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ocr_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    human_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column()
    confidence_source: Mapped[str | None] = mapped_column(String(50))
    correction_reason: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(255))
    decision: Mapped[str | None] = mapped_column(String(50))
    origin: Mapped[str | None] = mapped_column(String(50))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    application: Mapped[Application | None] = relationship(back_populates="feedback_entries")
    document: Mapped[Document | None] = relationship()
    ocr_result: Mapped[OCRResult | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<FeedbackEntry id={self.id} field={self.field_name}>"
