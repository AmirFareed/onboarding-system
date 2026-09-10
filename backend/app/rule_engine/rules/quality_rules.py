"""Data quality rules.

Rules that guard the quality of the extracted evidence itself: normalized
values must be cleanly formatted, no verified value may be empty, every field
must meet the configured confidence floor, and a reported transaction count
must be a positive integer.
"""

from app.database.models.enums import ValidationStatus
from app.rule_engine.constants import CONFIDENCE_FLOOR, NOTHING_TO_VALIDATE
from app.rule_engine.rules.base import BaseRule, RuleContext, RuleResult
from app.rule_engine.validators import is_positive_integer

#: Category every quality rule belongs to.
CATEGORY = "quality"


class QualityNormalizedValuesCleanRule(BaseRule):
    """Normalized values must have no stray surrounding or double whitespace."""

    id = "QUAL_NORMALIZED_VALUES_CLEAN"
    name = "Normalized values are cleanly formatted"
    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        normalized = [field for field in context.fields if field.normalized_value]
        if not normalized:
            return self.result(
                ValidationStatus.WARNING,
                NOTHING_TO_VALIDATE,
            )
        related_documents = sorted({field.document_id for field in normalized})
        for field in normalized:
            value = field.normalized_value or ""
            if value != value.strip() or "  " in value:
                return self.result(
                    ValidationStatus.FAIL,
                    f"Normalized value {value!r} of field {field.field_name} "
                    "has stray whitespace",
                    related_document_ids=[field.document_id],
                    related_field_names=[field.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "All normalized values are cleanly formatted",
            related_document_ids=related_documents,
        )


class QualityNoEmptyValuesRule(BaseRule):
    """No verified field may carry an empty extracted value."""

    id = "QUAL_NO_EMPTY_VALUES"
    name = "No verified field has an empty value"
    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not context.fields:
            return self.result(
                ValidationStatus.WARNING,
                NOTHING_TO_VALIDATE,
            )
        related_documents = sorted({field.document_id for field in context.fields})
        for field in context.fields:
            if not (field.extracted_value or "").strip():
                return self.result(
                    ValidationStatus.FAIL,
                    f"Field {field.field_name} has an empty extracted value",
                    related_document_ids=[field.document_id],
                    related_field_names=[field.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "No field has an empty extracted value",
            related_document_ids=related_documents,
        )


class QualityConfidenceFloorRule(BaseRule):
    """Every extracted field must meet the configured confidence floor."""

    id = "QUAL_CONFIDENCE_FLOOR"
    name = "Extracted fields meet the confidence floor"
    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not context.fields:
            return self.result(
                ValidationStatus.WARNING,
                NOTHING_TO_VALIDATE,
            )
        related_documents = sorted({field.document_id for field in context.fields})
        for field in context.fields:
            if (field.confidence_score or 0.0) < CONFIDENCE_FLOOR:
                return self.result(
                    ValidationStatus.FAIL,
                    f"Field {field.field_name} has confidence "
                    f"{field.confidence_score} below the floor {CONFIDENCE_FLOOR}",
                    related_document_ids=[field.document_id],
                    related_field_names=[field.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "All extracted fields meet the confidence floor",
            related_document_ids=related_documents,
        )


class QualityTransactionCountRule(BaseRule):
    """A reported transaction count must be a positive integer."""

    id = "QUAL_TRANSACTION_COUNT"
    name = "Transaction count is a positive integer"
    category = CATEGORY
    field_names = ("transaction_count",)

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = [
            field
            for field_name in self.field_names
            for field in context.values(field_name)
        ]
        if not values:
            return self.result(
                ValidationStatus.PASS,
                "No transaction count field is present to validate",
                related_field_names=list(self.field_names),
            )
        related_documents = sorted({field.document_id for field in values})
        for field in values:
            if not is_positive_integer(field.normalized_value):
                return self.result(
                    ValidationStatus.FAIL,
                    f"Transaction count {field.normalized_value!r} is not a "
                    "positive integer",
                    related_document_ids=[field.document_id],
                    related_field_names=list(self.field_names),
                )
        return self.result(
            ValidationStatus.PASS,
            "Transaction count is a positive integer",
            related_document_ids=related_documents,
            related_field_names=list(self.field_names),
        )


__all__ = [
    "QualityConfidenceFloorRule",
    "QualityNoEmptyValuesRule",
    "QualityNormalizedValuesCleanRule",
    "QualityTransactionCountRule",
]
