"""Pydantic models forming the validation report API contract.

The report is a read-only aggregation of data persisted by earlier pipeline
modules. These models mirror that aggregation -- application information,
per-document summary, extraction totals, business rule totals per group, the
visual detection summary and the deterministic recommendations -- without
binding to the ORM, keeping the API contract independent of persistence.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReportApplicationInfo(BaseModel):
    """Static application information shown at the top of a report.

    Attributes:
        application_id: Id of the application.
        name: Application or business name, if provided.
        status: Current ``applications.status`` value.
        submitted_at: Submission timestamp.
        updated_at: Last update timestamp.
        created_by: Creator of the application.
    """

    application_id: int
    name: str | None = None
    status: str
    submitted_at: datetime
    updated_at: datetime
    created_by: str


class ReportDocumentItem(BaseModel):
    """Per-document summary row.

    Attributes:
        document_id: Id of the document.
        document_type: Document type of the document.
        processing_status: Current processing status of the document.
        ocr_status: OCR/extraction outcome for the document.
        ocr_confidence: OCR confidence for the document, when available.
        technical_validation_status: Technical validation outcome for the
            document.
        analysis_status: Document analysis outcome for the document.
    """

    document_id: int
    document_type: str
    processing_status: str
    ocr_status: str
    ocr_confidence: float | None = None
    technical_validation_status: str
    analysis_status: str


class ReportExtractionSummary(BaseModel):
    """Aggregated extraction and verification totals.

    Attributes:
        total_fields: Number of extracted field rows.
        auto_verified: Fields verified automatically with high confidence.
        human_corrected: Fields confirmed or corrected by a human reviewer.
        pending_review: Fields still awaiting human review.
        cannot_verify: Fields the reviewer could not verify.
        overall_confidence: Mean confidence across the extracted fields.
    """

    total_fields: int
    auto_verified: int
    human_corrected: int
    pending_review: int
    cannot_verify: int
    overall_confidence: float | None = None


class ReportRuleCategorySummary(BaseModel):
    """Totals for a single report group.

    Attributes:
        category: Report group label (e.g. ``Signature Validation``).
        total: Number of stored rule rows in the group.
        passed: Rows that passed.
        failed: Rows that failed.
        warnings: Rows that warned.
        pending_manual_review: Rows awaiting manual review.
    """

    category: str
    total: int
    passed: int
    failed: int
    warnings: int
    pending_manual_review: int


class ReportRuleSummary(BaseModel):
    """Business rule execution totals, overall and per group.

    Attributes:
        total: Total number of stored business rule rows.
        passed: Rows that passed.
        failed: Rows that failed.
        warnings: Rows that warned.
        pending_manual_review: Rows awaiting manual review.
        by_category: Per-group totals in fixed display order.
    """

    total: int
    passed: int
    failed: int
    warnings: int
    pending_manual_review: int
    by_category: list[ReportRuleCategorySummary] = Field(default_factory=list)


class ReportVisualDetectionSummary(BaseModel):
    """Aggregated visual detection totals.

    Attributes:
        documents_checked: Number of documents with a stored detection outcome.
        signature_detected: Signatures reported present.
        signature_missing: Signatures reported absent.
        stamp_detected: Stamps reported present.
        stamp_missing: Stamps reported absent.
        average_confidence: Mean detection confidence, when available.
    """

    documents_checked: int
    signature_detected: int
    signature_missing: int
    stamp_detected: int
    stamp_missing: int
    average_confidence: float | None = None


class ReportRecommendation(BaseModel):
    """One deterministic recommendation.

    Attributes:
        code: Stable machine-readable recommendation identifier.
        message: Human-readable action for the reviewer.
    """

    code: str
    message: str


class ValidationReport(BaseModel):
    """The full validation report for an application.

    Attributes:
        application_id: Id of the application.
        report_version: Version of the report generator.
        generated_at: Timestamp the report was generated.
        application: Static application information.
        overall_status: Derived overall verdict of the report.
        document_summary: Per-document summary rows.
        extraction_summary: Extraction and verification totals.
        rule_summary: Business rule totals per group.
        visual_detection_summary: Visual detection totals.
        recommendations: Deterministic recommendation list.
    """

    application_id: int
    report_version: str
    generated_at: datetime
    application: ReportApplicationInfo
    overall_status: str
    document_summary: list[ReportDocumentItem] = Field(default_factory=list)
    extraction_summary: ReportExtractionSummary
    rule_summary: ReportRuleSummary
    visual_detection_summary: ReportVisualDetectionSummary
    recommendations: list[ReportRecommendation] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    """Condensed version of a validation report.

    Attributes:
        application_id: Id of the application.
        report_version: Version of the report generator.
        generated_at: Timestamp the summary was generated.
        overall_status: Derived overall verdict of the report.
        application_status: Current ``applications.status`` value.
        document_count: Number of uploaded documents.
        rule_total: Number of stored business rule rows.
        rule_passed: Business rule rows that passed.
        rule_failed: Business rule rows that failed.
        rule_warnings: Business rule rows that warned.
        rule_pending_review: Business rule rows awaiting manual review.
        field_count: Number of extracted field rows.
        overall_confidence: Mean field confidence, when available.
        recommendation_count: Number of recommendations.
    """

    application_id: int
    report_version: str
    generated_at: datetime
    overall_status: str
    application_status: str
    document_count: int
    rule_total: int
    rule_passed: int
    rule_failed: int
    rule_warnings: int
    rule_pending_review: int
    field_count: int
    overall_confidence: float | None = None
    recommendation_count: int


class ErrorResponse(BaseModel):
    """Standard error response body.

    Attributes:
        detail: Human-readable error description.
    """

    detail: str


__all__ = [
    "ErrorResponse",
    "ReportApplicationInfo",
    "ReportDocumentItem",
    "ReportExtractionSummary",
    "ReportRecommendation",
    "ReportRuleCategorySummary",
    "ReportRuleSummary",
    "ReportVisualDetectionSummary",
    "ValidationReport",
    "ValidationSummary",
]
