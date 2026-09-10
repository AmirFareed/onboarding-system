"""Policy compliance rules.

Banking-policy style checks on the account evidence: the account must be held
by a real named entity, the statement must reconcile, a single currency must be
used, and the salary month must fall inside the statement period when both are
present. Rules that depend on optional data warn when that data is absent.
"""

from decimal import Decimal, InvalidOperation

from app.database.models.enums import DocumentType, ValidationStatus
from app.rule_engine.constants import (
    NOTHING_TO_VALIDATE,
    RECONCILIATION_TOLERANCE,
)
from app.rule_engine.rules.base import (
    BaseRule,
    RuleContext,
    RuleResult,
    field_values,
    normalized_values,
)
from app.rule_engine.validators import is_placeholder

#: Category every policy rule belongs to.
CATEGORY = "policy"

#: Documents that carry account-level evidence for the policy rules.
TARGET_DOCUMENT_TYPES = frozenset({DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE})


def _as_decimal(value: str) -> Decimal | None:
    """Parse an amount string into a ``Decimal``, or ``None``."""
    try:
        return Decimal(value.replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


class PolicyAccountHolderRealRule(BaseRule):
    """The account holder must be a real named entity, not a placeholder."""

    id = "POL_ACCOUNT_HOLDER_REAL"
    name = "Account holder is a real named entity"
    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = normalized_values(
            context,
            "account_holder",
            document_types={item.value for item in TARGET_DOCUMENT_TYPES},
        )
        related_fields = ["account_holder"]
        if not values:
            return self.result(
                ValidationStatus.WARNING,
                NOTHING_TO_VALIDATE,
                related_field_names=related_fields,
            )
        for value in values:
            if is_placeholder(value):
                return self.result(
                    ValidationStatus.FAIL,
                    f"Account holder {value!r} is a placeholder, not a real entity",
                    related_field_names=related_fields,
                )
        related_documents = sorted(
            {
                item.document_id
                for item in field_values(
                    context,
                    "account_holder",
                    document_types={item.value for item in TARGET_DOCUMENT_TYPES},
                )
            }
        )
        return self.result(
            ValidationStatus.PASS,
            "Account holder is a real named entity",
            related_document_ids=related_documents,
            related_field_names=related_fields,
        )


class PolicyBalanceReconciliationRule(BaseRule):
    """The opening balance must reconcile with credits and debits.

    Uses the identity ``closing = opening + credits - debits`` on the same
    document, within the configured tolerance.
    """

    id = "POL_BALANCE_RECONCILIATION"
    name = "Opening balance reconciles with credits and debits"
    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        fields = {
            name: normalized_values(
                context,
                name,
                document_types={item.value for item in TARGET_DOCUMENT_TYPES},
            )
            for name in ("opening_balance", "closing_balance", "total_credits", "total_debits")
        }
        related_fields = list(fields)
        if not any(fields.values()):
            return self.result(
                ValidationStatus.WARNING,
                NOTHING_TO_VALIDATE,
                related_field_names=related_fields,
            )
        if not all(fields.values()):
            return self.result(
                ValidationStatus.WARNING,
                "A balance component is missing; the statement cannot be reconciled",
                related_field_names=related_fields,
            )
        opening = _as_decimal(fields["opening_balance"][0])
        closing = _as_decimal(fields["closing_balance"][0])
        credits = _as_decimal(fields["total_credits"][0])
        debits = _as_decimal(fields["total_debits"][0])
        if None in (opening, closing, credits, debits):
            return self.result(
                ValidationStatus.WARNING,
                "A balance value could not be parsed as an amount",
                related_field_names=related_fields,
            )
        expected = opening + credits - debits
        difference = abs(expected - closing)
        related_documents = sorted(
            {
                item.document_id
                for name in fields
                for item in field_values(
                    context,
                    name,
                    document_types={item.value for item in TARGET_DOCUMENT_TYPES},
                )
            }
        )
        if difference > RECONCILIATION_TOLERANCE:
            return self.result(
                ValidationStatus.FAIL,
                f"Closing balance {closing} does not reconcile with the opening "
                f"balance {opening}, credits {credits} and debits {debits} "
                f"(expected {expected})",
                related_document_ids=related_documents,
                related_field_names=related_fields,
            )
        return self.result(
            ValidationStatus.PASS,
            "Statement balances reconcile",
            related_document_ids=related_documents,
            related_field_names=related_fields,
        )


class PolicySingleCurrencyRule(BaseRule):
    """Exactly one currency must be used across the account evidence."""

    id = "POL_SINGLE_CURRENCY"
    name = "A single currency is used"
    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        currencies = normalized_values(
            context,
            "currency",
            document_types={item.value for item in TARGET_DOCUMENT_TYPES},
        )
        related_fields = ["currency"]
        if not currencies:
            return self.result(
                ValidationStatus.WARNING,
                NOTHING_TO_VALIDATE,
                related_field_names=related_fields,
            )
        related_documents = sorted(
            {
                item.document_id
                for item in field_values(
                    context,
                    "currency",
                    document_types={item.value for item in TARGET_DOCUMENT_TYPES},
                )
            }
        )
        if len(currencies) > 1:
            return self.result(
                ValidationStatus.FAIL,
                "Multiple currencies are used: "
                + ", ".join(sorted(f"{item!r}" for item in currencies)),
                related_document_ids=related_documents,
                related_field_names=related_fields,
            )
        return self.result(
            ValidationStatus.PASS,
            f"A single currency ({currencies[0]}) is used",
            related_document_ids=related_documents,
            related_field_names=related_fields,
        )


class PolicyPeriodSalaryAlignedRule(BaseRule):
    """The salary month must fall within the statement period when both exist.

    The rule only evaluates when both the payslip's salary month and the
    statement period are present; otherwise it warns, since there is nothing to
    align.
    """

    id = "POL_PERIOD_SALARY_ALIGNED"
    name = "Salary month falls within the statement period"
    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        months = normalized_values(context, "salary_month")
        periods = normalized_values(context, "statement_period")
        related_fields = ["salary_month", "statement_period"]
        if not months or not periods:
            return self.result(
                ValidationStatus.WARNING,
                "No salary month and statement period pair is present to compare",
                related_field_names=related_fields,
            )
        related_documents = sorted(
            {
                item.document_id
                for item in context.values("salary_month") + context.values("statement_period")
            }
        )
        for month in months:
            if len(month) != 7 or not month.startswith("20"):
                return self.result(
                    ValidationStatus.WARNING,
                    f"Salary month {month!r} is not in the canonical form",
                    related_document_ids=related_documents,
                    related_field_names=related_fields,
                )
            _month_year, _month_number = month.split("-", 1)
            for period in periods:
                if "-" not in period:
                    continue
                start_part, end_part = period.split(" - ", 1)
                start_date = f"{start_part[:7]}-01"
                end_date = f"{end_part[:7]}-01"
                if not (start_date <= f"{month}-01" <= end_date):
                    return self.result(
                        ValidationStatus.FAIL,
                        f"Salary month {month} falls outside the statement period "
                        f"{period}",
                        related_document_ids=related_documents,
                        related_field_names=related_fields,
                    )
        return self.result(
            ValidationStatus.PASS,
            "Salary month falls within the statement period",
            related_document_ids=related_documents,
            related_field_names=related_fields,
        )


__all__ = [
    "PolicyAccountHolderRealRule",
    "PolicyBalanceReconciliationRule",
    "PolicyPeriodSalaryAlignedRule",
    "PolicySingleCurrencyRule",
]
