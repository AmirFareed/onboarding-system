"""Pydantic schemas for the continuous learning module.

Every schema is used as the OpenAPI request/response model for the module's
endpoints. The ``LearningDatasetEntry`` schema is the presentation of one
curated training sample: the 12-field contract that pairs the noisy OCR value
with the trusted human-corrected value plus the provenance and quality context
needed for future OCR, extraction and document-AI improvements.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class LearningDatasetEntry(BaseModel):
    """A single curated, validated machine-learning sample.

    Attributes:
        application_id: Source application of the sample.
        document_type: Type of the source document, or ``UNKNOWN``.
        field_name: Name of the extracted field the sample describes.
        original_ocr_value: Value produced by the OCR pipeline.
        normalized_value: Canonical form of the value, if normalized.
        human_corrected_value: Value confirmed/corrected by a reviewer (label).
        confidence_score: Confidence assigned by the pipeline (0.0 - 1.0).
        confidence_source: Source that produced the confidence score.
        correction_reason: Optional explanation for the correction.
        decision: Review decision that produced the correction.
        origin: Whether the sample came from a low-confidence review or the
            final human review.
        recorded_at: When the source feedback was recorded (UTC).
    """

    application_id: int
    document_type: str
    field_name: str
    original_ocr_value: str
    normalized_value: str | None
    human_corrected_value: str
    confidence_score: float
    confidence_source: str | None
    correction_reason: str | None
    decision: str | None
    origin: str | None
    recorded_at: datetime


class DatasetMetadata(BaseModel):
    """Reproducible metadata describing one curated dataset.

    Attributes:
        dataset_version: Deterministic version identifier derived from the
            dataset schema version and the content hash.
        project_version: Version of the software that generated the dataset.
        created_at: When the dataset was generated (UTC).
        record_count: Number of curated records in the dataset.
        dataset_hash: SHA-256 digest of the canonical record serialization.
    """

    dataset_version: str
    project_version: str
    created_at: datetime
    record_count: int
    dataset_hash: str


class LearningDataset(BaseModel):
    """The curated dataset together with its metadata."""

    metadata: DatasetMetadata
    records: list[LearningDatasetEntry]


class DatasetStatistics(BaseModel):
    """Deterministic statistics over the curated dataset.

    Every distribution is ordered by key so the output is fully reproducible
    for the same dataset.
    """

    total_records: int
    document_distribution: dict[str, int]
    field_distribution: dict[str, int]
    correction_distribution: dict[str, int]
    confidence_distribution: dict[str, int]
    average_confidence: float | None
    reviewer_distribution: dict[str, int]
    dataset_completeness: dict[str, float]
    metadata: DatasetMetadata


class ExportResponse(BaseModel):
    """Result of a curated dataset export.

    Attributes:
        dataset_version: Version identifier of the exported dataset.
        created_at: When the export was generated (UTC).
        record_count: Number of records in the export.
        format: Export format identifier (``json`` or ``csv``).
        dataset_hash: SHA-256 digest of the canonical record serialization.
        project_version: Version of the software that generated the dataset.
        filename: Suggested filename for the exported dataset.
        content: The serialized dataset (JSON array or CSV text).
    """

    dataset_version: str
    created_at: datetime
    record_count: int
    format: str
    dataset_hash: str
    project_version: str
    filename: str
    content: str = Field(min_length=0)


class ErrorResponse(BaseModel):
    """Standard error envelope returned by the module's endpoints."""

    detail: str
