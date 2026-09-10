"""Extracted field model.

Stores one field extracted from the raw OCR text of a document. A field carries
the engine's extracted value, a confidence score, an optional normalized value
and the per-field confidence and human-verification state written by the
confidence scoring module. Field names must be unique per OCR result so a value
can never silently be overwritten.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.ocr_result import OCRResult


class ExtractedField(Base):
    """A single key/value field extracted from an OCR result.

    Attributes:
        id: Auto-incrementing primary key.
        ocr_result_id: Owning OCR result (foreign key, cascades on delete).
        field_name: Machine-readable name of the extracted field.
        extracted_value: Raw value as produced by the extraction engine.
        confidence_score: Extraction confidence for this field (0.0 - 1.0).
        normalized_value: Canonical form of the value, if normalization ran.
        confidence_source: Primary confidence source that produced the score.
        confidence_reason: Human-readable explanation of the score.
        verification_status: Per-field verification state (e.g. ``PENDING_REVIEW``).
        human_corrected_value: Value confirmed/corrected by a reviewer.
        human_verified: Whether a reviewer verified the field.
        reviewer: Name of the reviewer, once reviewed.
        reviewed_at: When the field was reviewed (UTC).
    """

    __tablename__ = "extracted_fields"
    __table_args__ = (
        Index("ix_extracted_fields_ocr_result_id", "ocr_result_id"),
        UniqueConstraint(
            "ocr_result_id",
            "field_name",
            name="uq_extracted_fields_ocr_result_id_field_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ocr_result_id: Mapped[int] = mapped_column(
        ForeignKey("ocr_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extracted_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column()
    normalized_value: Mapped[str | None] = mapped_column(Text)
    confidence_source: Mapped[str | None] = mapped_column(String(50))
    confidence_reason: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[str | None] = mapped_column(String(50))
    human_corrected_value: Mapped[str | None] = mapped_column(Text)
    human_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reviewer: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ocr_result: Mapped[OCRResult] = relationship(back_populates="extracted_fields")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ExtractedField id={self.id} name={self.field_name}>"
