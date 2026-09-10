"""Pydantic schemas for the confidence scoring module.

Every schema is used as the OpenAPI request/response model for the module's
endpoints, so the API contract is fully documented. The schemas are presentation
models: they mirror the evaluation outcome but never bind to the ORM directly,
keeping the API contract independent of the persistence layer.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.confidence.constants import (
    EvaluationStatus,
)


class ReviewDecisionType(StrEnum):
    """Decision an employee can make for one flagged field."""

    VERIFIED = "VERIFIED"
    CORRECTED = "CORRECTED"
    CANNOT_VERIFY = "CANNOT_VERIFY"


class FieldConfidenceResult(BaseModel):
    """Confidence and review state of one extracted field.

    Attributes:
        document_id: Document the field was extracted from.
        file_name: Original filename of the source document.
        field_name: Machine-readable name of the field.
        extracted_value: Value produced by the extraction engine.
        normalized_value: Canonical form of the value, when available.
        confidence_score: Field confidence (0.0 - 1.0).
        confidence_source: Source that contributed most to the score.
        confidence_reason: Human-readable explanation of the score.
        verification_status: Per-field verification state.
        critical: Whether the field is classified as critical.
        human_corrected_value: Value confirmed/corrected by a reviewer.
        human_verified: Whether a reviewer verified the field.
        reviewer: Name of the reviewer, once reviewed.
        reviewed_at: When the field was reviewed (UTC).
    """

    document_id: int
    file_name: str
    field_name: str
    extracted_value: str
    normalized_value: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_source: str
    confidence_reason: str
    verification_status: str
    critical: bool
    human_corrected_value: str | None = None
    human_verified: bool = False
    reviewer: str | None = None
    reviewed_at: datetime | None = None


class EvaluateResponse(BaseModel):
    """Result of evaluating an application's field confidence.

    Attributes:
        application_id: Evaluated application.
        processing_status: Overall outcome of the evaluation.
        overall_confidence: Mean field confidence across the application.
        threshold: Confidence threshold used for the decision.
        fields_requiring_review: Low-confidence fields returned for review,
            present only when the processing status requires human review.
        critical_failures: Critical fields whose confidence is below threshold.
    """

    application_id: int
    processing_status: EvaluationStatus
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    fields_requiring_review: list[FieldConfidenceResult] = []
    critical_failures: list[str] = []


class ReviewDecisionInput(BaseModel):
    """One employee decision for a flagged field.

    Attributes:
        field_name: Name of the flagged field being decided.
        decision: ``VERIFIED``, ``CORRECTED`` or ``CANNOT_VERIFY``.
        corrected_value: Required when the decision is ``CORRECTED``.
        reason: Optional explanation for the decision.
    """

    field_name: str = Field(min_length=1, max_length=255)
    decision: ReviewDecisionType
    corrected_value: str | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, max_length=1000)


class ReviewRequest(BaseModel):
    """Payload for submitting a human review.

    Attributes:
        decisions: One decision per flagged field; every flagged field must
            appear exactly once.
    """

    decisions: list[ReviewDecisionInput] = Field(min_length=1)


class ReviewResponse(BaseModel):
    """Result of applying a human review.

    Attributes:
        application_id: Reviewed application.
        processing_status: Final status after the review (ready for
            normalization or processing halted).
    """

    application_id: int
    processing_status: EvaluationStatus


class ErrorResponse(BaseModel):
    """Uniform error payload returned by the module's endpoints."""

    detail: str


__all__ = [
    "ErrorResponse",
    "EvaluateResponse",
    "FieldConfidenceResult",
    "ReviewDecisionInput",
    "ReviewDecisionType",
    "ReviewRequest",
    "ReviewResponse",
]
