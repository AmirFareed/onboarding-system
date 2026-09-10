"""Pydantic schemas for the document analysis module.

Every schema is used as the OpenAPI response model for the module's endpoints,
so the request/response contract is fully documented. The schemas are
presentation models: they mirror the analysis outcome but never bind to the ORM
directly, keeping the API contract independent of the persistence layer.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalysisOutcome(StrEnum):
    """Whether a document was analysed or its analysis failed."""

    ANALYZED = "ANALYZED"
    FAILED = "FAILED"


class FieldValidationResult(BaseModel):
    """Outcome of validating one extracted field.

    Attributes:
        field: Name of the validated field.
        validator: Identifier of the validator that ran.
        status: ``valid``, ``invalid`` or ``missing``.
        message: Human-readable explanation of the outcome.
    """

    field: str
    validator: str
    status: str
    message: str


class ConsistencyResult(BaseModel):
    """Outcome of one cross-field consistency check.

    Attributes:
        rule_id: Opaque identifier of the executed rule.
        rule_name: Human-readable rule name.
        status: ``pass``, ``fail``, ``warning`` or ``not_applicable``.
        message: Human-readable explanation of the outcome.
    """

    rule_id: str
    rule_name: str
    status: str
    message: str


class AnalysisSummary(BaseModel):
    """Headline verification outcome of one document."""

    status: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class AnalysisReport(BaseModel):
    """Explainable analysis report suitable for a review dashboard.

    Attributes:
        summary: Headline status and confidence score.
        fields: Normalized extracted fields keyed by field name.
        validations: Outcomes of every per-field validation.
        consistency_checks: Outcomes of every cross-field consistency check.
        issues: Human-readable list of problems found during analysis.
    """

    summary: AnalysisSummary
    fields: dict[str, Any]
    validations: list[FieldValidationResult]
    consistency_checks: list[ConsistencyResult]
    issues: list[str]


class DocumentAnalysisItem(BaseModel):
    """Outcome of analysing one document.

    Attributes:
        document_id: Analysed document.
        file_name: Original filename of the document.
        document_type: Detected analysed document category.
        outcome: Whether the document was analysed or failed.
        verification_status: Overall verification status, when analysed.
        confidence_score: Deterministic confidence score, when analysed.
        extracted_fields: Normalized extracted fields, when analysed.
        validation_results: Per-field validations, when analysed.
        consistency_results: Cross-field checks, when analysed.
        issues: Problems found during analysis, when analysed.
        processing_time_ms: Duration of the analysis in milliseconds.
        message: Failure reason when the document was not analysed.
    """

    document_id: int
    file_name: str
    document_type: str | None = None
    outcome: AnalysisOutcome
    verification_status: str | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    extracted_fields: dict[str, Any] | None = None
    validation_results: list[FieldValidationResult] | None = None
    consistency_results: list[ConsistencyResult] | None = None
    issues: list[str] | None = None
    processing_time_ms: int | None = Field(default=None, ge=0)
    message: str | None = None


class AnalyzeDocumentsResponse(BaseModel):
    """Result of a full analysis run over an application's documents."""

    application_id: int
    items: list[DocumentAnalysisItem]
    total_analyzed: int
    total_failed: int


class AnalysisResultItem(BaseModel):
    """One stored analysis result for a document."""

    model_config = ConfigDict(from_attributes=True)

    document_id: int
    file_name: str
    document_type: str
    verification_status: str
    confidence_score: float | None = None
    extracted_fields: dict[str, Any]
    validation_results: list[dict[str, Any]]
    consistency_results: list[dict[str, Any]]
    issues: list[str]
    processing_time_ms: int | None = None
    created_at: datetime
    updated_at: datetime


class AnalysisResultsResponse(BaseModel):
    """Every stored analysis result for an application."""

    application_id: int
    items: list[AnalysisResultItem]
    total: int


class ErrorResponse(BaseModel):
    """Uniform error payload returned by the module's endpoints."""

    detail: str
