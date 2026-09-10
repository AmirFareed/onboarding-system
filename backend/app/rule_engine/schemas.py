"""Schemas and shared data structures for the business rule engine.

Two families of types live here:

* In-memory data structures (``FieldValue``, ``RuleContext``, ``RuleResult``)
  that rules consume and produce. They are plain dataclasses, independent of
  the ORM, so every rule can be unit-tested by building a context by hand.
* Pydantic models that form the OpenAPI request/response contract of the
  module's endpoints. They mirror the run outcome but never bind to the ORM
  directly, keeping the API contract independent of the persistence layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field

from app.database.models.enums import ValidationStatus
from app.rule_engine.constants import RULE_CATEGORIES, RULE_ENGINE_VERSION


@dataclass(frozen=True)
class FieldValue:
    """One extracted field value the rule engine can inspect.

    Attributes:
        field_name: Machine-readable name of the field.
        document_id: Document the field was extracted from.
        document_type: Document type the field belongs to.
        extracted_value: Value produced by the extraction engine.
        normalized_value: Canonical form of the value, or ``None`` when
            normalization has not run (or failed) for the field.
        verification_status: Per-field verification state.
        confidence_score: Extraction confidence for the field (0.0 - 1.0).
    """

    field_name: str
    document_id: int
    document_type: str
    extracted_value: str
    normalized_value: str | None
    verification_status: str | None
    confidence_score: float | None = None


@dataclass
class RuleContext:
    """Everything a rule may inspect about an application.

    Rules are pure functions of this context, so they can be unit-tested
    without a database. The context is assembled once per run by the service.

    Attributes:
        application_id: Application being validated.
        documents_by_type: Document ids grouped by document type.
        fields: Every extracted field of the application.
        detections: Visual detection outcomes keyed by ``(document_id,
            detection_type)``; the value is whether the detection kind was
            present.
    """

    application_id: int
    documents_by_type: dict[str, list[int]]
    fields: list[FieldValue]
    detections: dict[tuple[int, str], bool] = field(default_factory=dict)

    def documents_of_type(self, document_type: str) -> list[int]:
        """Return the ids of the documents of ``document_type``."""
        return list(self.documents_by_type.get(document_type, []))

    def values(self, field_name: str) -> list[FieldValue]:
        """Return every field row named ``field_name``.

        Args:
            field_name: Machine-readable name of the field.

        Returns:
            The matching field rows in stable application order.
        """
        return [field for field in self.fields if field.field_name == field_name]

    def normalized_values(self, field_name: str) -> list[str]:
        """Return the non-empty normalized values of ``field_name``.

        Args:
            field_name: Machine-readable name of the field.

        Returns:
            The non-empty canonical values, deduplicated preserving order.
        """
        values: list[str] = []
        for entry in self.values(field_name):
            value = (entry.normalized_value or "").strip()
            if value and value not in values:
                values.append(value)
        return values

    def has_detection(self, document_id: int, detection_type: str) -> bool:
        """Return whether a detection outcome exists for a document and kind."""
        return (document_id, detection_type) in self.detections

    def is_detected(self, document_id: int, detection_type: str) -> bool:
        """Return whether the detection for a document and kind was present.

        Returns ``False`` when no detection outcome exists at all.
        """
        return self.detections.get((document_id, detection_type), False)


@dataclass
class RuleResult:
    """Outcome of executing one business rule.

    Attributes:
        rule_id: Opaque identifier of the rule.
        rule_name: Human-readable rule name.
        category: Category identifier the rule belongs to.
        status: Resolution state of the rule.
        message: Human-readable explanation of the outcome.
        related_document_ids: Documents the rule related to.
        related_field_names: Field names the rule related to.
        validated_at: When the rule executed (UTC), filled by the service.
    """

    rule_id: str
    rule_name: str
    category: str
    status: ValidationStatus
    message: str | None = None
    related_document_ids: list[int] = field(default_factory=list)
    related_field_names: list[str] = field(default_factory=list)
    validated_at: datetime | None = None

    def with_validated_at(self, validated_at: datetime) -> RuleResult:
        """Return a copy of the result stamped with ``validated_at``."""
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            category=self.category,
            status=self.status,
            message=self.message,
            related_document_ids=list(self.related_document_ids),
            related_field_names=list(self.related_field_names),
            validated_at=validated_at,
        )


# -- Pydantic response models --------------------------------------------------


class RuleResultItem(BaseModel):
    """One rule outcome in a validation response.

    Attributes:
        rule_id: Opaque identifier of the rule.
        rule_name: Human-readable rule name.
        category: Category identifier the rule belongs to.
        category_label: Human-readable category name.
        status: Resolution state of the rule.
        severity: Importance level derived from the status.
        message: Human-readable explanation of the outcome.
        related_document_ids: Documents the rule related to.
        related_field_names: Field names the rule related to.
        validated_at: When the rule executed (UTC).
    """

    rule_id: str
    rule_name: str
    category: str
    category_label: str
    status: ValidationStatus
    severity: str
    message: str | None = None
    related_document_ids: list[int] = Field(default_factory=list)
    related_field_names: list[str] = Field(default_factory=list)
    validated_at: datetime | None = None


class RuleCategorySummary(BaseModel):
    """Aggregate counts of one category within a validation run."""

    category: str
    category_label: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    pending_review: int = 0


class RuleRunSummary(BaseModel):
    """Aggregate counts of one validation run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    pending_review: int = 0


class RuleEngineResponse(BaseModel):
    """Result of validating an application against the business rules.

    Attributes:
        application_id: Validated application.
        validation_status: Overall outcome of the run.
        rule_engine_version: Version of the ruleset applied.
        validated_at: When the run executed (UTC).
        summary: Aggregate counts for the run.
        category_summary: Per-category aggregate counts.
        results: Detailed per-rule outcomes.
    """

    application_id: int
    validation_status: ValidationStatus
    rule_engine_version: str = RULE_ENGINE_VERSION
    validated_at: datetime
    summary: RuleRunSummary = RuleRunSummary()
    category_summary: list[RuleCategorySummary] = Field(default_factory=list)
    results: list[RuleResultItem] = Field(default_factory=list)


class StoredRuleResult(BaseModel):
    """One persisted rule-engine validation result row.

    Attributes:
        rule_id: Opaque identifier of the rule.
        rule_name: Human-readable rule name.
        rule_category: Category identifier the rule belongs to.
        category_label: Human-readable category name.
        status: Resolution state of the rule.
        severity: Importance level of the rule.
        message: Human-readable explanation of the outcome.
        related_document_ids: Documents the rule related to.
        related_field_names: Field names the rule related to.
        validated_at: When the rule executed (UTC).
    """

    rule_id: str
    rule_name: str
    rule_category: str
    category_label: str
    status: ValidationStatus
    severity: str
    message: str | None = None
    related_document_ids: list[int] = Field(default_factory=list)
    related_field_names: list[str] = Field(default_factory=list)
    validated_at: datetime


class ValidationResultsResponse(BaseModel):
    """Stored rule-engine validation results for an application.

    Attributes:
        application_id: Application the results belong to.
        total: Number of stored result rows returned.
        results: The stored per-rule outcome rows.
    """

    application_id: int
    total: int
    results: list[StoredRuleResult] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Uniform error payload returned by the module's endpoints."""

    detail: str


def category_label(category: str) -> str:
    """Return the human-readable label for ``category``.

    Args:
        category: Category identifier.

    Returns:
        The configured label, or the identifier when unknown.
    """
    return RULE_CATEGORIES.get(category, category)


__all__ = [
    "ErrorResponse",
    "FieldValue",
    "RuleCategorySummary",
    "RuleContext",
    "RuleEngineResponse",
    "RuleResult",
    "RuleResultItem",
    "RuleRunSummary",
    "StoredRuleResult",
    "ValidationResultsResponse",
    "category_label",
]
