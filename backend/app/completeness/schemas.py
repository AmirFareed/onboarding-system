"""Pydantic schemas for the completeness module.

These models shape the structured completeness report returned by both the
``GET`` and ``POST`` completeness endpoints. Uploaded documents reuse the upload
module's public metadata model so the same read model serves both modules.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.completeness.constants import CompletenessStatus
from app.database.models.enums import DocumentType
from app.upload.schemas import DocumentMetadata


class RequiredDocumentStatus(BaseModel):
    """Presence of a single mandatory document type for an application."""

    document_type: DocumentType
    is_present: bool
    copy_count: int = Field(ge=0)


class DuplicateDocumentInfo(BaseModel):
    """A configured document type uploaded more than once."""

    document_type: DocumentType
    copy_count: int = Field(gt=1, description="Number of copies of this type.")


class UnexpectedDocumentInfo(BaseModel):
    """A document type outside the configured required/optional catalogue."""

    document_type: DocumentType
    copy_count: int = Field(ge=1, description="Number of copies of this type.")


class ErrorResponse(BaseModel):
    """Envelope used for every completeness error response."""

    detail: str = Field(examples=["Application not found"])


class CompletenessReport(BaseModel):
    """Structured result of a completeness verification.

    Attributes:
        application_id: Id of the verified application.
        status: Overall completeness status.
        uploaded_documents: Metadata of every document uploaded for the
            application.
        required_documents: Presence status of every mandatory document type.
        missing_documents: Required types that have no uploaded copy.
        duplicate_documents: Configured types uploaded more than once.
        unexpected_documents: Types outside the configured catalogue.
        completion_percentage: Percentage of required types present (0-100).
        timestamp: When the verification was run (UTC).
    """

    model_config = ConfigDict(from_attributes=True)

    application_id: int
    status: CompletenessStatus
    uploaded_documents: list[DocumentMetadata]
    required_documents: list[RequiredDocumentStatus]
    missing_documents: list[DocumentType]
    duplicate_documents: list[DuplicateDocumentInfo]
    unexpected_documents: list[UnexpectedDocumentInfo]
    completion_percentage: float = Field(ge=0.0, le=100.0)
    timestamp: datetime
