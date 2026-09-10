"""Cross-field consistency rules and verification scoring.

Consistency rules reason over several extracted fields at once (e.g. whether the
closing balance reconciles against opening balance and credits/debits) and are
stored separately from the per-field validations. The scoring functions combine
extraction coverage, validation rate and consistency rate into a single
deterministic confidence score and derive the explainable verification status.
"""

from datetime import date, datetime
from typing import Any

from app.document_analysis.constants import (
    BALANCE_EPSILON,
    CRITICAL_FIELDS,
    EXPECTED_FIELDS,
    NEEDS_REVIEW_MIN_SCORE,
    PARTIALLY_VERIFIED_MIN_SCORE,
    SCORE_WEIGHT_CONSISTENCY,
    SCORE_WEIGHT_FIELD_COVERAGE,
    SCORE_WEIGHT_VALIDATION,
    VERIFIED_MIN_SCORE,
    AnalyzedDocumentType,
    VerificationStatus,
)

RuleResult = dict[str, str]


def _rule(rule_id: str, rule_name: str, status: str, message: str) -> RuleResult:
    """Build a serializable consistency result dict."""
    return {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "status": status,
        "message": message,
    }


# -- Bank statement rules -----------------------------------------------------


def statement_period_valid(fields: dict[str, Any]) -> RuleResult:
    """The statement period start must not be after its end."""
    period = fields.get("statement_period")
    if not isinstance(period, dict):
        return _rule(
            "STMT_PERIOD_VALID", "Statement period is valid", "not_applicable",
            "Statement period not available",
        )
    try:
        start = datetime.strptime(period["start"], "%Y-%m-%d").date()
        end = datetime.strptime(period["end"], "%Y-%m-%d").date()
    except (KeyError, TypeError, ValueError):
        return _rule(
            "STMT_PERIOD_VALID", "Statement period is valid", "fail",
            "Statement period dates could not be parsed",
        )
    if start > end:
        return _rule(
            "STMT_PERIOD_VALID", "Statement period is valid", "fail",
            "Statement period starts after it ends",
        )
    return _rule(
        "STMT_PERIOD_VALID", "Statement period is valid", "pass",
        "Statement period start is before its end",
    )


def opening_le_closing(fields: dict[str, Any]) -> RuleResult:
    """The opening balance should not exceed the closing balance.

    A closing balance below the opening balance is possible when withdrawals
    exceed deposits, so a violation is reported as a warning rather than a hard
    failure.
    """
    opening = fields.get("opening_balance")
    closing = fields.get("closing_balance")
    if opening is None or closing is None:
        return _rule(
            "OPENING_LE_CLOSING", "Opening balance not above closing", "not_applicable",
            "Opening or closing balance not available",
        )
    if opening > closing + BALANCE_EPSILON:
        return _rule(
            "OPENING_LE_CLOSING", "Opening balance not above closing", "warning",
            "Closing balance is below the opening balance; possible withdrawals",
        )
    return _rule(
        "OPENING_LE_CLOSING", "Opening balance not above closing", "pass",
        "Opening balance is not above the closing balance",
    )


def closing_balance_matches_transactions(fields: dict[str, Any]) -> RuleResult:
    """Reconcile the closing balance against opening and transaction totals.

    When total credits and debits are available the closing balance must equal
    ``opening + credits - debits``. Otherwise a statement with no transactions
    must keep its balance unchanged; statements with activity but no totals can
    only be flagged for manual verification.
    """
    opening = fields.get("opening_balance")
    closing = fields.get("closing_balance")
    credits = fields.get("total_credits")
    debits = fields.get("total_debits")
    count = fields.get("transaction_count")

    if opening is not None and closing is not None and credits is not None and debits is not None:
        expected = opening + credits - debits
        if abs(closing - expected) <= BALANCE_EPSILON:
            return _rule(
                "CLOSING_MATCHES_TRANSACTIONS", "Closing balance matches transactions",
                "pass", "Closing balance reconciles with credits and debits",
            )
        return _rule(
            "CLOSING_MATCHES_TRANSACTIONS", "Closing balance matches transactions",
            "fail",
            "Closing balance does not reconcile with opening balance and transaction totals",
        )
    if opening is not None and closing is not None and count == 0:
        if abs(closing - opening) <= BALANCE_EPSILON:
            return _rule(
                "CLOSING_MATCHES_TRANSACTIONS", "Closing balance matches transactions",
                "pass", "Closing balance unchanged with no transactions",
            )
        return _rule(
            "CLOSING_MATCHES_TRANSACTIONS", "Closing balance matches transactions",
            "fail", "Closing balance changed despite no transactions",
        )
    return _rule(
        "CLOSING_MATCHES_TRANSACTIONS", "Closing balance matches transactions",
        "warning", "Exact reconciliation requires per-transaction line items",
    )


def balances_non_negative(fields: dict[str, Any]) -> RuleResult:
    """Both statement balances must be non-negative."""
    opening = fields.get("opening_balance")
    closing = fields.get("closing_balance")
    if opening is None or closing is None:
        return _rule(
            "BALANCES_NON_NEGATIVE", "Balances are non-negative", "not_applicable",
            "Opening or closing balance not available",
        )
    if opening < 0 or closing < 0:
        return _rule(
            "BALANCES_NON_NEGATIVE", "Balances are non-negative", "fail",
            "A balance is negative",
        )
    return _rule(
        "BALANCES_NON_NEGATIVE", "Balances are non-negative", "pass",
        "Opening and closing balances are non-negative",
    )


# -- Payslip rules ------------------------------------------------------------


def net_le_gross(fields: dict[str, Any]) -> RuleResult:
    """Net salary must not exceed gross salary."""
    gross = fields.get("gross_salary")
    net = fields.get("net_salary")
    if gross is None or net is None:
        return _rule(
            "NET_LE_GROSS", "Net salary does not exceed gross", "not_applicable",
            "Gross or net salary not available",
        )
    if net > gross + BALANCE_EPSILON:
        return _rule(
            "NET_LE_GROSS", "Net salary does not exceed gross", "fail",
            "Net salary exceeds gross salary",
        )
    return _rule(
        "NET_LE_GROSS", "Net salary does not exceed gross", "pass",
        "Net salary is not above gross salary",
    )


def net_positive(fields: dict[str, Any]) -> RuleResult:
    """Net salary must be non-negative."""
    net = fields.get("net_salary")
    if net is None:
        return _rule(
            "NET_POSITIVE", "Net salary is positive", "not_applicable",
            "Net salary not available",
        )
    if net < 0:
        return _rule(
            "NET_POSITIVE", "Net salary is positive", "fail",
            "Net salary is negative",
        )
    return _rule(
        "NET_POSITIVE", "Net salary is positive", "pass",
        "Net salary is non-negative",
    )


def payment_date_within_month(fields: dict[str, Any]) -> RuleResult:
    """The payment date must fall in the salary month or the following month.

    Payroll is commonly settled on the last working day of the month or shortly
    into the next month, so both are accepted.
    """
    payment = fields.get("payment_date")
    salary_month = fields.get("salary_month")
    if payment is None or salary_month is None:
        return _rule(
            "PAYMENT_WITHIN_MONTH", "Payment date within salary month", "not_applicable",
            "Payment date or salary month not available",
        )
    try:
        pay = datetime.strptime(payment, "%Y-%m-%d").date()
        salary_year, salary_month_number = (int(part) for part in salary_month.split("-"))
    except (ValueError, AttributeError):
        return _rule(
            "PAYMENT_WITHIN_MONTH", "Payment date within salary month", "fail",
            "Payment date or salary month could not be parsed",
        )
    next_month = salary_month_number % 12 + 1
    next_year = salary_year + (1 if salary_month_number == 12 else 0)
    same_month = pay.year == salary_year and pay.month == salary_month_number
    following_month = pay.year == next_year and pay.month == next_month
    if not same_month and not following_month:
        return _rule(
            "PAYMENT_WITHIN_MONTH", "Payment date within salary month", "fail",
            "Payment date is outside the salary month",
        )
    return _rule(
        "PAYMENT_WITHIN_MONTH", "Payment date within salary month", "pass",
        "Payment date falls within the salary month",
    )


# -- Identity rules -----------------------------------------------------------


def expiry_after_issue(fields: dict[str, Any]) -> RuleResult:
    """The expiry date must be after the issue date."""
    issue = fields.get("issue_date")
    expiry = fields.get("expiry_date")
    if issue is None:
        return _rule(
            "EXPIRY_AFTER_ISSUE", "Expiry date after issue date", "not_applicable",
            "Issue date not available",
        )
    if expiry is None:
        return _rule(
            "EXPIRY_AFTER_ISSUE", "Expiry date after issue date", "not_applicable",
            "Expiry date not available",
        )
    try:
        issue_date = datetime.strptime(issue, "%Y-%m-%d").date()
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    except ValueError:
        return _rule(
            "EXPIRY_AFTER_ISSUE", "Expiry date after issue date", "fail",
            "Issue or expiry date could not be parsed",
        )
    if expiry_date <= issue_date:
        return _rule(
            "EXPIRY_AFTER_ISSUE", "Expiry date after issue date", "fail",
            "Expiry date is not after the issue date",
        )
    return _rule(
        "EXPIRY_AFTER_ISSUE", "Expiry date after issue date", "pass",
        "Expiry date is after the issue date",
    )


def age_reasonable(fields: dict[str, Any]) -> RuleResult:
    """The age derived from the date of birth must be between 0 and 120."""
    dob = fields.get("date_of_birth")
    if dob is None:
        return _rule(
            "AGE_REASONABLE", "Age is reasonable", "not_applicable",
            "Date of birth not available",
        )
    try:
        born = datetime.strptime(dob, "%Y-%m-%d").date()
    except ValueError:
        return _rule(
            "AGE_REASONABLE", "Age is reasonable", "fail",
            "Date of birth could not be parsed",
        )
    today = date.today()
    if born > today:
        return _rule(
            "AGE_REASONABLE", "Age is reasonable", "fail",
            "Date of birth is in the future",
        )
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age > 120:
        return _rule(
            "AGE_REASONABLE", "Age is reasonable", "fail",
            "Age exceeds 120 years",
        )
    return _rule(
        "AGE_REASONABLE", "Age is reasonable", "pass",
        f"Age ({age} years) is plausible",
    )


# -- Tax rules ----------------------------------------------------------------


def gross_positive(fields: dict[str, Any]) -> RuleResult:
    """Gross income must be non-negative."""
    gross = fields.get("gross_income")
    if gross is None:
        return _rule(
            "GROSS_POSITIVE", "Gross income is positive", "not_applicable",
            "Gross income not available",
        )
    if gross < 0:
        return _rule(
            "GROSS_POSITIVE", "Gross income is positive", "fail",
            "Gross income is negative",
        )
    return _rule(
        "GROSS_POSITIVE", "Gross income is positive", "pass",
        "Gross income is non-negative",
    )


def tax_not_exceeding_gross(fields: dict[str, Any]) -> RuleResult:
    """Total tax must not exceed gross income."""
    gross = fields.get("gross_income")
    tax = fields.get("total_tax")
    if gross is None or tax is None:
        return _rule(
            "TAX_NOT_EXCEEDING_GROSS", "Tax does not exceed gross income", "not_applicable",
            "Gross income or total tax not available",
        )
    if tax > gross + BALANCE_EPSILON:
        return _rule(
            "TAX_NOT_EXCEEDING_GROSS", "Tax does not exceed gross income", "fail",
            "Total tax exceeds gross income",
        )
    return _rule(
        "TAX_NOT_EXCEEDING_GROSS", "Tax does not exceed gross income", "pass",
        "Total tax is within gross income",
    )


#: Consistency rules executed for each analysed document type, in order.
_TYPE_RULES: dict[AnalyzedDocumentType, list[tuple[str, str, Any]]] = {
    AnalyzedDocumentType.BANK_STATEMENT: [
        ("STMT_PERIOD_VALID", "Statement period is valid", statement_period_valid),
        ("OPENING_LE_CLOSING", "Opening balance not above closing", opening_le_closing),
        (
            "CLOSING_MATCHES_TRANSACTIONS",
            "Closing balance matches transactions",
            closing_balance_matches_transactions,
        ),
        ("BALANCES_NON_NEGATIVE", "Balances are non-negative", balances_non_negative),
    ],
    AnalyzedDocumentType.PAYSLIP: [
        ("NET_LE_GROSS", "Net salary does not exceed gross", net_le_gross),
        ("NET_POSITIVE", "Net salary is positive", net_positive),
        ("PAYMENT_WITHIN_MONTH", "Payment date within salary month", payment_date_within_month),
    ],
    AnalyzedDocumentType.ID_DOCUMENT: [
        ("EXPIRY_AFTER_ISSUE", "Expiry date after issue date", expiry_after_issue),
        ("AGE_REASONABLE", "Age is reasonable", age_reasonable),
    ],
    AnalyzedDocumentType.TAX_DOCUMENT: [
        ("GROSS_POSITIVE", "Gross income is positive", gross_positive),
        ("TAX_NOT_EXCEEDING_GROSS", "Tax does not exceed gross income", tax_not_exceeding_gross),
    ],
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: [],
}


class RulesEngine:
    """Executes the cross-field consistency rules for a document type."""

    def run(self, document_type: AnalyzedDocumentType, fields: dict[str, Any]) -> list[RuleResult]:
        """Run every consistency rule applicable to ``document_type``.

        Args:
            document_type: Analysed document type selecting the rules.
            fields: Normalized extracted fields.

        Returns:
            A list of consistency result dicts in a fixed rule order.
        """
        rules = _TYPE_RULES.get(document_type, [])
        return [rule(fields) for _, _, rule in rules]


# -- Scoring ------------------------------------------------------------------


def compute_score(
    *,
    field_coverage: float,
    validation_rate: float,
    consistency_rate: float,
) -> float:
    """Combine the three component rates into a single confidence score.

    ``field_coverage`` is the fraction of expected fields extracted,
    ``validation_rate`` the fraction of field validations that passed and
    ``consistency_rate`` the fraction of applicable consistency checks that
    passed. The weighted sum is clamped to ``[0.0, 1.0]``.

    Args:
        field_coverage: Extracted fields / expected fields.
        validation_rate: Passing validations / total validations.
        consistency_rate: Passing checks / applicable checks.

    Returns:
        The deterministic confidence score.
    """
    score = (
        SCORE_WEIGHT_FIELD_COVERAGE * field_coverage
        + SCORE_WEIGHT_VALIDATION * validation_rate
        + SCORE_WEIGHT_CONSISTENCY * consistency_rate
    )
    return max(0.0, min(1.0, score))


def compute_verification_status(
    score: float,
    *,
    missing_critical_fields: bool,
    critical_validation_failures: bool,
    consistency_failures: bool,
) -> VerificationStatus:
    """Derive the verification status from the score and decisive failures.

    Missing critical fields, failed validations of critical fields or any failed
    consistency check force manual review regardless of the score. Otherwise the
    score thresholds map to ``VERIFIED``, ``PARTIALLY_VERIFIED``,
    ``NEEDS_REVIEW`` and ``FAILED``.

    Args:
        score: The computed confidence score.
        missing_critical_fields: Whether any critical field is missing.
        critical_validation_failures: Whether a critical field failed validation.
        consistency_failures: Whether any consistency check failed.

    Returns:
        The derived verification status.
    """
    if missing_critical_fields or critical_validation_failures or consistency_failures:
        return VerificationStatus.NEEDS_REVIEW
    if score >= VERIFIED_MIN_SCORE:
        return VerificationStatus.VERIFIED
    if score >= PARTIALLY_VERIFIED_MIN_SCORE:
        return VerificationStatus.PARTIALLY_VERIFIED
    if score >= NEEDS_REVIEW_MIN_SCORE:
        return VerificationStatus.NEEDS_REVIEW
    return VerificationStatus.FAILED


def scoring_components(
    document_type: AnalyzedDocumentType,
    *,
    fields: dict[str, Any],
    validation_results: list[dict[str, str]],
    consistency_results: list[RuleResult],
) -> tuple[float, float, float, VerificationStatus]:
    """Compute all scoring inputs for a document type in one place.

    Args:
        document_type: Analysed document type.
        fields: Normalized extracted fields.
        validation_results: Per-field validation outcomes.
        consistency_results: Cross-field consistency outcomes.

    Returns:
        ``(field_coverage, validation_rate, consistency_rate, score, status)``.
    """
    expected = EXPECTED_FIELDS.get(document_type, frozenset())
    present = sum(1 for field in expected if fields.get(field) is not None)
    field_coverage = present / len(expected) if expected else 0.0

    total_validations = len(validation_results)
    passing_validations = sum(
        1 for result in validation_results if result["status"] == "valid"
    )
    validation_rate = (
        passing_validations / total_validations if total_validations else 1.0
    )

    applicable = [r for r in consistency_results if r["status"] != "not_applicable"]
    passing_consistency = sum(1 for r in applicable if r["status"] == "pass")
    consistency_rate = passing_consistency / len(applicable) if applicable else 1.0

    critical = CRITICAL_FIELDS.get(document_type, frozenset())
    missing_critical = any(fields.get(field) is None for field in critical)
    critical_validation_failures = any(
        result["status"] == "invalid" and result["field"] in critical
        for result in validation_results
    )
    consistency_failures = any(
        result["status"] == "fail" for result in consistency_results
    )

    score = compute_score(
        field_coverage=field_coverage,
        validation_rate=validation_rate,
        consistency_rate=consistency_rate,
    )
    status = compute_verification_status(
        score,
        missing_critical_fields=missing_critical,
        critical_validation_failures=critical_validation_failures,
        consistency_failures=consistency_failures,
    )
    return field_coverage, validation_rate, consistency_rate, score, status
