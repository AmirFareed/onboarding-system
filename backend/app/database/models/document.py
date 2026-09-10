"""Document model.

Stores metadata for an uploaded document belonging to an application. The file
bytes themselves live on the storage backend; the database keeps provenance and
processing state. A document has at most one OCR result.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import DocumentProcessingStatus, DocumentType

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.ocr_result import OCRResult
    from app.database.models.queue_job import QueueJob
    from app.database.models.visual_detection import VisualDetection


class Document(Base):
    """Metadata record for one uploaded document.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Owning application (foreign key, cascades on delete).
        document_type: Category of the document.
        copy_number: 1-based slot index for this copy within the document type
            (e.g. the second 1-Link form is copy_number 2). Defaults to 1 so
            pre-existing single-copy rows are unaffected.
        original_filename: Filename supplied by the uploader.
        stored_file_path: Location of the file on the storage backend.
        file_type: Media type (MIME) of the stored file.
        uploaded_at: When the document was uploaded (UTC).
        processing_status: Stage of the processing pipeline for this document.
    """

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_application_id", "application_id"),
        Index("ix_documents_document_type", "document_type"),
        Index("ix_documents_processing_status", "processing_status"),
        Index("ix_documents_uploaded_at", "uploaded_at"),
        #: A numbered copy slot can hold exactly one file per application.
        Index(
            "ix_documents_app_type_copy",
            "application_id",
            "document_type",
            "copy_number",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[DocumentType] = mapped_column(nullable=False)
    copy_number: Mapped[int] = mapped_column(
        default=1,
        server_default="1",
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        default=DocumentProcessingStatus.PENDING,
        server_default=text("'PENDING'"),
        nullable=False,
    )

    application: Mapped[Application] = relationship(back_populates="documents")
    ocr_result: Mapped[OCRResult | None] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    visual_detections: Mapped[list[VisualDetection]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    queue_jobs: Mapped[list[QueueJob]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Document id={self.id} type={self.document_type}>"
