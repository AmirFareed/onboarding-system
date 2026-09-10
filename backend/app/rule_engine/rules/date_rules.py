"""Date and period rules.

Every rule works on the canonical ``YYYY-MM-DD`` values produced by the
normalization module, so no format guessing is needed here. A rule with no
value to evaluate warns instead of failing, because the pipeline had nothing
to confirm. Times are compared against the run's own clock, which keeps the
rules deterministic for a given run instant.
"""

from datetime import UTC, date, datetime, timedelta

from app.database.models.enums import ValidationStatus
from app.rule_engine.constants import (
    MIN_BIRTH_YEAR,
    NOTHING_TO_VALIDATE,
    STATEMENT_MAX_AGE_DAYS,
)
from app.rule_engine.rules.base import BaseRule, RuleContext, RuleResult, normalized_values

#: Category every date rule belongs to.
CATEGORY = "date"

_PERIOD_SEPARATOR = " - "


def _parse_iso(value: str) -> date | None:
    """Parse a canonical ``YYYY-MM-DD`` value into a date, or ``None``."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_period(value: str) -> tuple[date, date] | None:
    """Parse a normalized period into its start and end dates, or ``None``."""
    if _PERIOD_SEPARATOR not in value:
        return None
    start, end = value.split(_PERIOD_SEPARATOR, 1)
    start_date = _parse_iso(start)
    end_date = _parse_iso(end)
    if start_date is None or end_date is None:
        return None
    return start_date, end_date


def _today() -> date:
    """Return the current date in the UTC timezone."""
    return datetime.now(UTC).date()


class _DateRule(BaseRule):
    """Base rule for single-field date checks with a nothing-to-validate path.

    Attributes:
        field_name: Field the rule inspects.
    """

    field_name: str

    category = CATEGORY

    def _nothing_to_validate(self) -> RuleResult:
        """Build the warning returned when no normalized value exists."""
        return self.result(
            ValidationStatus.WARNING,
            NOTHING_TO_VALIDATE,
            related_field_names=[self.field_name],
        )

    def _evaluate_value(self, context: RuleContext, value: str, document_id: int) -> RuleResult:
        """Evaluate the rule against one normalized value."""
        raise NotImplementedError  # pragma: no cover - abstract

    def _evaluate_presence(self, context: RuleContext, present_message: str) -> RuleResult:
        """Fail when the field is present but blank; warn when never extracted."""
        matching_fields = [f for f in context.fields if f.field_name == self.field_name]
        valid_values = normalized_values(context, self.field_name)
        if not valid_values and matching_fields:
            return self.result(
                ValidationStatus.FAIL,
                f"Required field {self.field_name} is missing or blank",
                related_document_ids=sorted({f.document_id for f in matching_fields}),
                related_field_names=[self.field_name],
            )
        if not valid_values:
            return self._nothing_to_validate()

        return self.result(
            ValidationStatus.PASS,
            present_message,
            related_document_ids=sorted({f.document_id for f in matching_fields}),
            related_field_names=[self.field_name],
        )


class DatePeriodSequenceRule(_DateRule):
    """The statement period must be chronological (start before or on end)."""

    id = "DATE_PERIOD_SEQUENCE"
    name = "Statement period is chronological"
    field_name = "statement_period"

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = normalized_values(context, self.field_name)
        if not values:
            return self._nothing_to_validate()
        related_documents = [
            value.document_id for value in context.values(self.field_name)
        ]
        for value in values:
            period = _parse_period(value)
            if period is None:
                return self.result(
                    ValidationStatus.WARNING,
                    f"Statement period {value!r} could not be parsed",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
            start, end = period
            if start > end:
                return self.result(
                    ValidationStatus.FAIL,
                    f"Statement period starts {start.isoformat()} after it "
                    f"ends {end.isoformat()}",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "Statement period is chronological",
            related_document_ids=sorted(related_documents),
            related_field_names=[self.field_name],
        )


class DatePeriodRangeRule(_DateRule):
    """The statement period must not be in the future and must be recent.

    A period that ends in the future fails; a period older than the configured
    age warns (the data may be stale rather than wrong).
    """

    id = "DATE_PERIOD_WITHIN_RANGE"
    name = "Statement period is recent and not in the future"
    field_name = "statement_period"

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = normalized_values(context, self.field_name)
        if not values:
            return self._nothing_to_validate()
        related_documents = [
            value.document_id for value in context.values(self.field_name)
        ]
        today = _today()
        oldest = today - timedelta(days=STATEMENT_MAX_AGE_DAYS)
        for value in values:
            period = _parse_period(value)
            if period is None:
                return self.result(
                    ValidationStatus.WARNING,
                    f"Statement period {value!r} could not be parsed",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
            _, end = period
            if end > today:
                return self.result(
                    ValidationStatus.FAIL,
                    f"Statement period ends {end.isoformat()}, which is in the future",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
            if end < oldest:
                return self.result(
                    ValidationStatus.WARNING,
                    f"Statement period ends {end.isoformat()}, which is older "
                    f"than {STATEMENT_MAX_AGE_DAYS} days",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "Statement period is within the accepted range",
            related_document_ids=sorted(related_documents),
            related_field_names=[self.field_name],
        )


class DateIssuePrecedesExpiryRule(_DateRule):
    """The issue date must precede the expiry date.

    Requires both dates; either missing means the check cannot be made and the
    rule warns.
    """

    id = "DATE_ISSUE_PRECEDES_EXPIRY"
    name = "Issue date precedes expiry date"
    field_name = "issue_date"

    def evaluate(self, context: RuleContext) -> RuleResult:
        issues = normalized_values(context, "issue_date")
        expiries = normalized_values(context, "expiry_date")
        if not issues or not expiries:
            return self.result(
                ValidationStatus.WARNING,
                "No issue and expiry date pair is present to compare",
                related_field_names=["issue_date", "expiry_date"],
            )
        related_documents = sorted(
            {
                value.document_id
                for value in context.values("issue_date") + context.values("expiry_date")
            }
        )
        for issue in issues:
            issue_date = _parse_iso(issue)
            if issue_date is None:
                return self.result(
                    ValidationStatus.WARNING,
                    f"Issue date {issue!r} could not be parsed",
                    related_document_ids=related_documents,
                    related_field_names=["issue_date"],
                )
            for expiry in expiries:
                expiry_date = _parse_iso(expiry)
                if expiry_date is None:
                    continue
                if issue_date >= expiry_date:
                    return self.result(
                        ValidationStatus.FAIL,
                        f"Issue date {issue} does not precede expiry date {expiry}",
                        related_document_ids=related_documents,
                        related_field_names=["issue_date", "expiry_date"],
                    )
        return self.result(
            ValidationStatus.PASS,
            "Issue dates precede their expiry dates",
            related_document_ids=related_documents,
            related_field_names=["issue_date", "expiry_date"],
        )


class DatePaymentRecencyRule(_DateRule):
    """The payment date must not be in the future."""

    id = "DATE_PAYMENT_RECENCY"
    name = "Payment date is not in the future"
    field_name = "payment_date"

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = normalized_values(context, self.field_name)
        if not values:
            return self._nothing_to_validate()
        related_documents = [
            value.document_id for value in context.values(self.field_name)
        ]
        today = _today()
        for value in values:
            payment_date = _parse_iso(value)
            if payment_date is None:
                return self.result(
                    ValidationStatus.WARNING,
                    f"Payment date {value!r} could not be parsed",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
            if payment_date > today:
                return self.result(
                    ValidationStatus.FAIL,
                    f"Payment date {value} is in the future",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "Payment dates are not in the future",
            related_document_ids=sorted(related_documents),
            related_field_names=[self.field_name],
        )


class DateDobSanityRule(_DateRule):
    """The date of birth must be plausible (after the minimum year, not future)."""

    id = "DATE_DOB_SANITY"
    name = "Date of birth is plausible"
    field_name = "date_of_birth"

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = normalized_values(context, self.field_name)
        if not values:
            return self._nothing_to_validate()
        related_documents = [
            value.document_id for value in context.values(self.field_name)
        ]
        today = _today()
        for value in values:
            dob = _parse_iso(value)
            if dob is None:
                return self.result(
                    ValidationStatus.WARNING,
                    f"Date of birth {value!r} could not be parsed",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
            if dob.year < MIN_BIRTH_YEAR or dob > today:
                return self.result(
                    ValidationStatus.FAIL,
                    f"Date of birth {value} is not plausible",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "Dates of birth are plausible",
            related_document_ids=sorted(related_documents),
            related_field_names=[self.field_name],
        )


__all__ = [
    "DateCnicNotExpiredRule",
    "DateDobSanityRule",
    "DateExpiryPresenceRule",
    "DateIssuePrecedesExpiryRule",
    "DateIssuePresenceRule",
    "DatePaymentRecencyRule",
    "DatePeriodRangeRule",
    "DatePeriodSequenceRule",
]


class DateIssuePresenceRule(_DateRule):
    """The issue date must be present."""

    id = "DATE_ISSUE_PRESENT"
    name = "Issue date is present"
    field_name = "issue_date"

    def evaluate(self, context: RuleContext) -> RuleResult:
        return self._evaluate_presence(context, "Issue dates are present")


class DateExpiryPresenceRule(_DateRule):
    """The expiry date must be present."""

    id = "DATE_EXPIRY_PRESENT"
    name = "Expiry date is present"
    field_name = "expiry_date"

    def evaluate(self, context: RuleContext) -> RuleResult:
        return self._evaluate_presence(context, "Expiry dates are present")


class DateCnicNotExpiredRule(_DateRule):
    """A CNIC's expiry date must not be in the past.

    Uses ``date_of_expiry`` -- CnicFrontExtractor's own field name, distinct
    from the generic ``expiry_date`` the other date rules share -- so this
    rule only ever evaluates a real CNIC's expiry, never an unrelated
    document's expiry field by coincidence.
    """

    id = "DATE_CNIC_NOT_EXPIRED"
    name = "CNIC is not expired"
    field_name = "date_of_expiry"

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = normalized_values(context, self.field_name)
        if not values:
            return self._nothing_to_validate()
        related_documents = [
            value.document_id for value in context.values(self.field_name)
        ]
        today = _today()
        for value in values:
            expiry = _parse_iso(value)
            if expiry is None:
                return self.result(
                    ValidationStatus.WARNING,
                    f"Date of expiry {value!r} could not be parsed",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
            if expiry < today:
                return self.result(
                    ValidationStatus.FAIL,
                    f"CNIC expired on {expiry.isoformat()}",
                    related_document_ids=sorted(related_documents),
                    related_field_names=[self.field_name],
                )
        return self.result(
            ValidationStatus.PASS,
            "CNIC is not expired",
            related_document_ids=sorted(related_documents),
            related_field_names=[self.field_name],
        )
