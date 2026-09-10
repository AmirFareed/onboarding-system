"""OCR result model.

Captures the outcome of running an OCR engine over a document. Each document has
exactly one OCR result (enforced by the unique foreign key). The raw text and
per-document confidence feed the extraction and rule-engine phases. The document
processing module writes the extraction metrics (processing method, page count,
character count and completion timestamp) into the additive nullable columns;
they stay ``NULL`` for any row written by a future OCR-writing module.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.document import Document
    from app.database.models.extracted_field import ExtractedField


class OCRResult(Base):
    """Result of running OCR on a document.

    Attributes:
        id: Auto-incrementing primary key.
        document_id: Document that was processed (unique foreign key).
        raw_ocr_text: Full raw text produced by the OCR engine.
        ocr_engine: Identifier of the OCR engine used.
        processing_time_ms: Wall-clock duration of the OCR run in milliseconds.
        overall_confidence: Engine-reported confidence for the whole document.
        processing_method: How the text was obtained (native text extraction
            or OCR over rendered pages).
        page_count: Number of pages that contributed to the extracted text.
        character_count: Length of the extracted text in characters.
        processed_at: When the extraction completed (UTC).
    """

    __tablename__ = "ocr_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    raw_ocr_text: Mapped[str] = mapped_column(Text, nullable=False)
    ocr_engine: Mapped[str] = mapped_column(String(100), nullable=False)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    overall_confidence: Mapped[float | None] = mapped_column()
    processing_method: Mapped[str | None] = mapped_column(String(50))
    page_count: Mapped[int | None] = mapped_column(Integer)
    character_count: Mapped[int | None] = mapped_column(Integer)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="ocr_result")
    extracted_fields: Mapped[list[ExtractedField]] = relationship(
        back_populates="ocr_result",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OCRResult id={self.id} document_id={self.document_id}>"
