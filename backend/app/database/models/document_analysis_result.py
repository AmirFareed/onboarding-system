"""Document analysis result model.

Captures the outcome of analysing the extracted text of one document: the
detected document type, the structured fields extracted from the OCR text, the
per-field validations, the cross-field consistency checks, and the deterministic
confidence score and verification status. Each document has exactly one analysis
result (unique foreign key); re-analysing replaces the previous row. The JSONB
columns store the full, explainable report so a frontend review dashboard can
render it without recomputation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.document import Document


class DocumentAnalysisResult(Base):
    """Structured analysis of one document's extracted text.

    Attributes:
        id: UUID primary key.
        application_id: Owning application (foreign key, cascades on delete).
        document_id: Analysed document (unique foreign key, cascades).
        document_type: Analysed document category (e.g. ``BANK_STATEMENT``).
        extracted_fields: Normalized key/value fields extracted from the text.
        validation_results: Per-field validation outcomes.
        consistency_results: Cross-field consistency check outcomes.
        confidence_score: Deterministic overall confidence (0.0 - 1.0).
        verification_status: Overall status (e.g. ``PARTIALLY_VERIFIED``).
        analysis_version: Version of the extraction/scoring logic used.
        processing_time_ms: Wall-clock duration of the analysis in milliseconds.
        created_at: When the analysis was first persisted (UTC).
        updated_at: When the analysis was last updated (UTC).
    """

    __tablename__ = "document_analysis_results"
    __table_args__ = (
        Index("ix_document_analysis_results_application_id", "application_id"),
        Index("ix_document_analysis_results_document_id", "document_id"),
        Index("ix_document_analysis_results_verification_status", "verification_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    extracted_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_results: Mapped[list] = mapped_column(JSONB, nullable=False)
    consistency_results: Mapped[list] = mapped_column(JSONB, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    verification_status: Mapped[str] = mapped_column(String(50), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(20), nullable=False)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    document: Mapped[Document] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<DocumentAnalysisResult id={self.id} "
            f"document_id={self.document_id} status={self.verification_status}>"
        )
