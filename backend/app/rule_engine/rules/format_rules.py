"""Field format rules.

Each rule verifies that the normalized values of a set of fields satisfy the
field's canonical format contract. The predicates come from the normalization
module's validators (IBAN, date shapes) or this module's validators (amounts,
account numbers). A rule with no normalized values to check warns, because it
cannot confirm the format and the pipeline simply had nothing to validate.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.database.models.enums import ValidationStatus
from app.normalization.validators import (
    is_canonical_cnic,
    is_canonical_iban,
    is_canonical_iso_date,
)
from app.rule_engine.constants import NOTHING_TO_VALIDATE
from app.rule_engine.rules.base import BaseRule, RuleContext, RuleResult
from app.rule_engine.validators import is_canonical_amount, is_valid_account_number

#: Category every format rule belongs to.
CATEGORY = "format"


class _FormatRule(BaseRule):
    """Base rule checking a set of fields against a canonical predicate.

    Attributes:
        field_names: Fields whose normalized values are checked.
        predicate: Predicate that must hold for every normalized value.
    """

    field_names: tuple[str, ...]
    predicate: Callable[[str], bool]

    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = [
            value
            for field_name in self.field_names
            for value in context.values(field_name)
            if (value.normalized_value or "").strip()
        ]
        related_documents = sorted({value.document_id for value in values})
        related_fields = [name for name in self.field_names if context.values(name)]
        if not values:
            return self.result(
                ValidationStatus.WARNING,
                NOTHING_TO_VALIDATE,
                related_field_names=related_fields,
            )
        for value in values:
            if not type(self).predicate(value.normalized_value):
                return self.result(
                    ValidationStatus.FAIL,
                    f"Value {value.normalized_value!r} of field "
                    f"{value.field_name} does not have the required format",
                    related_document_ids=[value.document_id],
                    related_field_names=[value.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "Every checked value has the required format",
            related_document_ids=related_documents,
            related_field_names=related_fields,
        )


class FormatIbanRule(_FormatRule):
    """Every IBAN value must match the canonical IBAN shape."""

    id = "FMT_IBAN"
    name = "IBAN has the canonical format"
    field_names = ("iban",)
    predicate = is_canonical_iban


class FormatCnicRule(_FormatRule):
    """Identity numbers must match the canonical CNIC shape.

    Applies only to fields expected to hold an identity-card number; employee
    identifiers are intentionally not covered.
    """

    id = "FMT_CNIC"
    name = "Identity numbers have the canonical format"
    field_names = ("document_number", "tax_reference_number")
    predicate = is_canonical_cnic


class FormatAccountNumberRule(_FormatRule):
    """Account numbers must be 6-20 letters or digits."""

    id = "FMT_ACCOUNT_NUMBER"
    name = "Account number has a valid format"
    field_names = ("account_number",)
    predicate = is_valid_account_number


class FormatAmountRule(_FormatRule):
    """Monetary amounts must match the canonical amount shape."""

    id = "FMT_AMOUNT"
    name = "Monetary amounts have a valid format"
    field_names = (
        "opening_balance",
        "closing_balance",
        "total_credits",
        "total_debits",
    )
    predicate = is_canonical_amount


class FormatDateShapeRule(_FormatRule):
    """Date fields must use the canonical ISO date shape."""

    id = "FMT_DATE_SHAPE"
    name = "Dates use the canonical format"
    field_names = (
        "date_of_birth",
        "issue_date",
        "expiry_date",
        "payment_date",
    )
    predicate = is_canonical_iso_date


__all__ = [
    "FormatAccountNumberRule",
    "FormatAmountRule",
    "FormatCnicRule",
    "FormatDateShapeRule",
    "FormatEStampRule",
    "FormatIbanRule",
]

ESTAMP_PATTERN = re.compile(r"^STAMP-\d{6}$", re.IGNORECASE)

class FormatEStampRule(_FormatRule):
    """E-Stamps must match the regex pattern STAMP-XXXXXX."""

    id = "FMT_ESTAMP"
    name = "E-Stamp has a valid format"
    field_names = ("e_stamp_id",)
    
    @staticmethod
    def predicate(value: str) -> bool:
        return ESTAMP_PATTERN.fullmatch(value) is not None
