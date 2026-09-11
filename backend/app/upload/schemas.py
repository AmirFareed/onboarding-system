"""Pydantic schemas for the upload API.

Uploads themselves are ``multipart/form-data`` (a file plus a document type), so
the request is described by FastAPI form parameters rather than a JSON schema.
These models shape the response payloads and the documented error envelope.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import DocumentProcessingStatus, DocumentType
from app.database.schemas import ApplicationRead


class DocumentMetadata(BaseModel):
    """Public document metadata, deliberately excluding internal storage paths.

    The database row carries ``stored_file_path`` but it must never be exposed
    to clients; this model shapes every response so the internal storage layout
    stays hidden.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    document_type: DocumentType
    copy_number: int
    original_filename: str
    file_type: str
    uploaded_at: datetime
    processing_status: DocumentProcessingStatus


class ApplicationCreateRequest(BaseModel):
    """Payload for creating a new application."""

    notes: str | None = Field(
        default=None,
        examples=["Checking account maintenance certificate."],
        description="Optional free-form notes.",
    )


class ApplicationCreateResponse(BaseModel):
    """Response returned after creating an application."""

    message: str = Field(examples=["Application created successfully"])
    application: ApplicationRead


class ApplicationListResponse(BaseModel):
    """Paginated list of applications."""

    items: list[ApplicationRead]
    total: int


class ApplicationDetailResponse(BaseModel):
    """Response returned when fetching a single application."""

    message: str = Field(examples=["Application found"])
    application: ApplicationRead


class DocumentUploadResponse(BaseModel):
    """Response returned after a successful document upload."""

    message: str = Field(examples=["Document uploaded successfully"])
    document: DocumentMetadata


class DocumentReplaceResponse(BaseModel):
    """Response returned after replacing an existing document."""

    message: str = Field(examples=["Document replaced successfully"])
    document: DocumentMetadata


class DocumentListResponse(BaseModel):
    """Paginated list of documents belonging to an application."""

    items: list[DocumentMetadata]
    total: int


class DocumentDeleteResponse(BaseModel):
    """Response returned after deleting a document."""

    message: str = Field(examples=["Document deleted successfully"])


class ApplicationDeleteResponse(BaseModel):
    """Response returned after deleting an application."""

    message: str = Field(examples=["Application deleted successfully"])


class ApplicationsClearedResponse(BaseModel):
    """Response returned after clearing all application history."""

    message: str = Field(examples=["All application history cleared successfully"])
    deleted_count: int = Field(examples=[41])


class BulkUploadSplitItem(BaseModel):
    """Metadata for a single document extracted during a bulk upload split."""

    document_type: DocumentType
    document: DocumentMetadata


class BulkUploadResponse(BaseModel):
    """Response returned after a bulk PDF is split and stored."""

    message: str = Field(examples=["Bulk PDF split into 9 documents successfully"])
    documents_created: int
    documents: list[BulkUploadSplitItem]


class ErrorResponse(BaseModel):
    """Envelope used for every upload error response."""

    detail: str = Field(
        examples=["A document of this type already exists for the application"]
    )
