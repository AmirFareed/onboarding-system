"""Pydantic schemas for the operator validation workflow."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import ApplicationStatus, DocumentType, ValidationEventType


class DocumentStatusSummary(BaseModel):
    """Business-level presence of a single required document type."""

    document_type: DocumentType
    is_present: bool
    copy_count: int = Field(ge=0)


class ValidationQueueItem(BaseModel):
    """One application in the operator validation queue.

    Deliberately business-facing: only status, completeness counts and the last
    workflow event -- never OCR confidence, processing or normalization
    internals.
    """

    model_config = ConfigDict(from_attributes=True)

    application_id: int
    application_name: str | None
    status: ApplicationStatus
    submitted_at: datetime
    updated_at: datetime
    created_by: str
    required_document_count: int = Field(ge=0)
    received_document_count: int = Field(ge=0)
    missing_document_count: int = Field(ge=0)
    missing_documents: list[DocumentType]
    required_documents: list[DocumentStatusSummary]
    completion_percentage: float = Field(ge=0.0, le=100.0)
    needs_attention: bool
    last_event_type: ValidationEventType | None
    last_event_at: datetime | None


class ValidationQueueResponse(BaseModel):
    """Paginated operator validation queue."""

    items: list[ValidationQueueItem]
    total: int
    offset: int
    limit: int


class ValidationHistoryEntryRead(BaseModel):
    """One immutable application-level validation workflow event."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: ValidationEventType
    actor_name: str | None
    actor_role: str | None
    previous_status: ApplicationStatus | None
    new_status: ApplicationStatus | None
    missing_document_types: list[str] | None
    document_ids: list[int] | None
    reason: str | None
    created_at: datetime


class ValidationHistoryResponse(BaseModel):
    """Paginated application validation history, newest first."""

    application_id: int
    entries: list[ValidationHistoryEntryRead]
    total: int
    offset: int
    limit: int


class RequestDocumentsRequest(BaseModel):
    """Operator request for missing documents on an application."""

    missing_document_types: list[DocumentType] = Field(
        min_length=1,
        description="Document types the customer/business must provide.",
    )
    reason: str | None = Field(default=None, max_length=2000)


class OperatorRejectRequest(BaseModel):
    """Operator rejection of an incomplete application."""

    reason: str = Field(min_length=1, max_length=2000)


class OperatorActionResponse(BaseModel):
    """Result of an operator action on an application."""

    application_id: int
    status: ApplicationStatus
    message: str
    history_entry_id: int | None = None


class ErrorResponse(BaseModel):
    """Envelope used for every operator workflow error response."""

    detail: str = Field(examples=["Application not found"])