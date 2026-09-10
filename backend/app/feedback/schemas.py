"""Pydantic schemas for the feedback module.

Every schema is used as the OpenAPI request/response model for the module's
endpoints, so the API contract is fully documented. The entry schema is the
presentation of a single dataset sample: it exposes the 14 canonical fields
that the confidence scoring and final human verification phases enrich at write
time, keeping the module read-mostly.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import DocumentType


class FeedbackFilters(BaseModel):
    """Query parameters used to narrow the feedback dataset.

    All filters are optional; when several are present they are combined with
    AND semantics.
    """

    application_id: int | None = Field(default=None, ge=1)
    reviewer: str | None = Field(default=None, max_length=255)
    document_type: DocumentType | None = None
    field_name: str | None = Field(default=None, max_length=255)
    decision: str | None = Field(default=None, max_length=50)
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class FeedbackEntry(BaseModel):
    """A single feedback dataset sample.

    Attributes:
        id: Dataset primary key.
        application_id: Source application, if still present.
        document_id: Document the corrected field was extracted from.
        ocr_result_id: OCR result the corrected field belongs to.
        field_name: Name of the field the sample describes.
        original_ocr_value: Value extracted by the OCR pipeline.
        normalized_value: Canonical form of the value, if normalized.
        human_corrected_value: Value confirmed/corrected by a reviewer.
        confidence_score: Confidence assigned by the pipeline (0.0 - 1.0).
        confidence_source: Source that produced the confidence score.
        correction_reason: Optional explanation for the correction.
        reviewer: Name of the reviewer who corrected the field.
        decision: Review decision that produced the correction.
        origin: Whether the correction came from a low-confidence review or
            the final human review.
        recorded_at: When the sample was recorded (UTC).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int | None
    document_id: int | None
    ocr_result_id: int | None
    field_name: str
    original_ocr_value: str | None
    normalized_value: str | None
    human_corrected_value: str
    confidence_score: float | None
    confidence_source: str | None
    correction_reason: str | None
    reviewer: str | None
    decision: str | None
    origin: str | None
    recorded_at: datetime


class FeedbackSummary(BaseModel):
    """A paginated slice of the feedback dataset."""

    total: int
    offset: int
    limit: int
    returned: int
    items: list[FeedbackEntry]


class FieldCount(BaseModel):
    """Number of corrections recorded for one field name."""

    field_name: str
    count: int


class DailyFrequency(BaseModel):
    """Number of corrections recorded on one calendar day (UTC)."""

    date: date
    count: int


class FeedbackStatistics(BaseModel):
    """Deterministic aggregation of the feedback dataset.

    Every distribution is ordered by key and ties are broken by name so the
    output is fully reproducible for the same dataset and filters.
    """

    total_entries: int
    total_corrected_fields: int
    most_corrected_fields: list[FieldCount]
    average_confidence: float | None
    corrections_by_reviewer: dict[str, int]
    corrections_by_document_type: dict[str, int]
    corrections_by_decision: dict[str, int]
    correction_frequency: list[DailyFrequency]
    generated_at: datetime


class ExportResponse(BaseModel):
    """Result of an export request.

    Attributes:
        format: Export format identifier (``json`` or ``csv``).
        filename: Suggested filename for the exported dataset.
        record_count: Number of entries included in the export.
        generated_at: When the export was generated (UTC).
        content: The serialized dataset (JSON array or CSV text).
    """

    format: str
    filename: str
    record_count: int
    generated_at: datetime
    content: str


class ErrorResponse(BaseModel):
    """Standard error envelope returned by the module's endpoints."""

    detail: str
