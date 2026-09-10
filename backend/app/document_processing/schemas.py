"""Pydantic schemas for the document processing module.

Every schema is used as the OpenAPI response model for the module's endpoints,
so the request/response contract is fully documented. The schemas are
presentation models: they mirror the extraction metrics but never bind to the
ORM directly.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.document_processing.constants import ProcessingMethod


class ProcessingOutcome(StrEnum):
    """Whether a document was processed, skipped or failed."""

    PROCESSED = "PROCESSED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class DocumentProcessingResult(BaseModel):
    """Outcome of processing one document."""

    document_id: int
    file_name: str
    outcome: ProcessingOutcome
    processing_method: ProcessingMethod | None = None
    ocr_engine: str | None = None
    page_count: int | None = None
    character_count: int | None = None
    processing_time_ms: int | None = Field(default=None, ge=0)
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_text: str | None = None
    message: str | None = None


class ProcessDocumentsResponse(BaseModel):
    """Result of a full processing run over an application's documents."""

    application_id: int
    items: list[DocumentProcessingResult]
    total_processed: int
    total_skipped: int
    total_failed: int


class OcrResultItem(BaseModel):
    """One stored OCR/text extraction result."""

    model_config = ConfigDict(from_attributes=True)

    document_id: int
    file_name: str
    raw_ocr_text: str
    ocr_engine: str
    processing_method: str | None = None
    processing_time_ms: int | None = None
    overall_confidence: float | None = None
    page_count: int | None = None
    character_count: int | None = None
    processed_at: datetime | None = None


class OcrResultsResponse(BaseModel):
    """Every stored OCR/text extraction result for an application."""

    application_id: int
    items: list[OcrResultItem]
    total: int


class ErrorResponse(BaseModel):
    """Uniform error payload returned by the module's endpoints."""

    detail: str
