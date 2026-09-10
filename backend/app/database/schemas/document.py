"""Pydantic schemas for the Document entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import DocumentProcessingStatus, DocumentType


class DocumentBase(BaseModel):
    """Common document attributes shared by all variants."""

    application_id: int
    document_type: DocumentType
    original_filename: str = Field(min_length=1, max_length=255)
    stored_file_path: str = Field(min_length=1, max_length=1024)
    file_type: str = Field(min_length=1, max_length=100)


class DocumentCreate(DocumentBase):
    """Payload for creating a new document record."""

    processing_status: DocumentProcessingStatus = DocumentProcessingStatus.PENDING


class DocumentStatusUpdate(BaseModel):
    """Payload for updating a document's processing status."""

    processing_status: DocumentProcessingStatus


class DocumentRead(DocumentBase):
    """Serialized document including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uploaded_at: datetime
    processing_status: DocumentProcessingStatus
