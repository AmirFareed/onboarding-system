"""Pydantic schemas for the technical validation API.

A :class:`TechnicalValidationReport` describes the outcome of validating a
single uploaded document; the list response wraps the reports produced for an
application. Only technical quality is reported -- no document contents, OCR
text or extracted fields ever appear here.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.database.models.enums import ValidationStatus
from app.technical_validation.constants import ReadabilityStatus, RotationStatus


class TechnicalValidationReport(BaseModel):
    """Structured report for the technical validation of one document.

    Attributes:
        application_id: Application the document belongs to.
        document_id: Validated document.
        file_name: Original filename of the document.
        file_type: Normalized detected format (e.g. ``PDF``, ``JPEG``, ``PNG``).
        validation_timestamp: When the validation run completed (UTC).
        validation_status: Overall outcome (``PASS``, ``FAIL``, ``WARNING``).
        file_accessible: Whether the stored file exists, is readable and
            non-empty.
        file_type_valid: Whether the format is accepted for processing.
        pdf_valid: Whether the PDF opened, is unencrypted, has pages and valid
            dimensions (``None`` for non-PDF documents).
        image_valid: Whether the image loaded and meets the minimum resolution
            (``None`` for non-image documents).
        blur_score: Variance-of-Laplacian sharpness score (``None`` when the
            document could not be rendered for analysis).
        rotation_angle: Estimated rotation in degrees (``None`` when not
            analysable).
        rotation_status: Whether the document appears rotated.
        readability_status: Overall technical readability without OCR.
        failed_checks: Human-readable names of the checks that failed.
        warnings: Human-readable names of the checks that raised warnings.
        recommendations: Actionable guidance derived from the checks.
    """

    application_id: int
    document_id: int
    file_name: str
    file_type: str
    validation_timestamp: datetime
    validation_status: ValidationStatus
    file_accessible: bool
    file_type_valid: bool
    pdf_valid: bool | None = Field(default=None)
    image_valid: bool | None = Field(default=None)
    blur_score: float | None = Field(default=None)
    rotation_angle: float | None = Field(default=None)
    rotation_status: RotationStatus
    readability_status: ReadabilityStatus
    failed_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class TechnicalValidationListResponse(BaseModel):
    """Reports produced for every validated document of an application."""

    application_id: int
    items: list[TechnicalValidationReport] = Field(default_factory=list)
    total: int


class ErrorResponse(BaseModel):
    """Envelope used for every technical validation error response."""

    detail: str = Field(
        examples=["Application not found"],
        description="Human-readable description of the failure.",
    )
