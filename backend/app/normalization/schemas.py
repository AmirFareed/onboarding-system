"""Pydantic schemas for the data normalization module.

Every schema is used as the OpenAPI request/response model for the module's
endpoints, so the API contract is fully documented. The schemas are presentation
models: they mirror the normalization outcome but never bind to the ORM
directly, keeping the API contract independent of the persistence layer.
"""


from pydantic import BaseModel

from app.normalization.constants import (
    NORMALIZATION_VERSION,
    NormalizationOutcome,
    NormalizationStatus,
)


class NormalizedFieldItem(BaseModel):
    """One extracted field and its normalization result.

    Attributes:
        document_id: Document the field was extracted from.
        file_name: Original filename of the source document.
        field_name: Machine-readable name of the field.
        source_value: Value the normalizer received (the verified value).
        normalized_value: Canonical form of the value, when available.
        normalizer: Identifier of the normalizer that processed the field.
        status: Per-field outcome (``NORMALIZED``, ``SKIPPED`` or ``FAILED``).
        reason: Human-readable explanation of the outcome.
    """

    document_id: int
    file_name: str
    field_name: str
    source_value: str
    normalized_value: str | None = None
    normalizer: str
    status: NormalizationOutcome
    reason: str | None = None


class NormalizationSummary(BaseModel):
    """Aggregate counts for one normalization run."""

    total: int = 0
    normalized: int = 0
    skipped: int = 0
    failed: int = 0


class NormalizeResponse(BaseModel):
    """Result of normalizing an application's verified fields.

    Attributes:
        application_id: Normalized application.
        processing_status: Overall outcome of the normalization run.
        normalization_version: Version of the normalization logic applied.
        items: Per-field normalization results.
        summary: Aggregate counts for the run.
    """

    application_id: int
    processing_status: NormalizationStatus
    normalization_version: str = NORMALIZATION_VERSION
    items: list[NormalizedFieldItem] = []
    summary: NormalizationSummary = NormalizationSummary()


class NormalizedFieldRecord(BaseModel):
    """A stored extracted field with its persisted normalized value.

    Attributes:
        document_id: Document the field was extracted from.
        file_name: Original filename of the source document.
        field_name: Machine-readable name of the field.
        extracted_value: Value produced by the extraction engine.
        normalized_value: Canonical form of the value, when available.
        verification_status: Per-field verification state.
    """

    document_id: int
    file_name: str
    field_name: str
    extracted_value: str
    normalized_value: str | None = None
    verification_status: str


class ErrorResponse(BaseModel):
    """Uniform error payload returned by the module's endpoints."""

    detail: str


__all__ = [
    "ErrorResponse",
    "NormalizationSummary",
    "NormalizeResponse",
    "NormalizedFieldItem",
    "NormalizedFieldRecord",
]
