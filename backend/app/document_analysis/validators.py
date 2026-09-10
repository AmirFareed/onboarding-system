"""Reusable field validators for the analysis pipeline.

Validators are pure functions mapping an extracted value to a status and
message, so they can be unit-tested in isolation and composed per document type.
Every validator returns ``("valid", message)`` or ``("invalid", message)``;
missing expected fields are reported separately by the engine as ``missing``.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.document_analysis.constants import EXPECTED_FIELDS, AnalyzedDocumentType

ValidationOutcome = tuple[str, str]


def _ok(message: str) -> ValidationOutcome:
    """Build a passing validation outcome."""
    return ("valid", message)


def _bad(message: str) -> ValidationOutcome:
    """Build a failing validation outcome."""
    return ("invalid", message)


def validate_required_presence(_value: Any) -> ValidationOutcome:
    """A present value always passes this placeholder validator."""
    return _ok("Field is present")


def validate_amount(value: Any) -> ValidationOutcome:
    """A monetary value must be a finite non-negative number."""
    if not isinstance(value, (int, float)) or value < 0:
        return _bad("Amount must be a non-negative number")
    return _ok("Amount is a valid non-negative number")


def validate_balance(value: Any) -> ValidationOutcome:
    """A balance must be a finite number; negative values need an overdraft flag."""
    if not isinstance(value, (int, float)):
        return _bad("Balance must be a number")
    if value < 0:
        return _bad("Balance is negative")
    return _ok("Balance is a valid number")


def validate_currency(value: Any) -> ValidationOutcome:
    """A currency must be a three-letter ISO 4217 code."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        return _bad("Currency must be a three-letter ISO code")
    return _ok("Currency is a valid ISO 4217 code")


def validate_iban(value: Any) -> ValidationOutcome:
    """Validate an IBAN's structure and ISO 13616 mod-97 checksum.

    Args:
        value: The IBAN as extracted from the document.

    Returns:
        ``valid`` when the IBAN passes both format and checksum, ``invalid``
        otherwise.
    """
    if not isinstance(value, str):
        return _bad("IBAN must be a string")
    iban = value.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        return _bad("IBAN has an invalid format")
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    if int(digits) % 97 != 1:
        return _bad("IBAN checksum failed")
    return _ok("IBAN checksum passed")


def validate_account_number(value: Any) -> ValidationOutcome:
    """An account number must be 4-30 digits (dashes/spaces permitted)."""
    if not isinstance(value, str):
        return _bad("Account number must be a string")
    cleaned = re.sub(r"[^0-9]", "", value)
    if len(cleaned) < 4 or len(cleaned) > 30:
        return _bad("Account number length is not plausible")
    return _ok("Account number is plausible")


def validate_document_number(value: Any) -> ValidationOutcome:
    """A document number must be 4-20 alphanumeric characters."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9\-]{4,20}", value):
        return _bad("Document number format is invalid")
    return _ok("Document number format is valid")


def validate_date(value: Any) -> ValidationOutcome:
    """An ISO ``YYYY-MM-DD`` date must be parseable and real.

    Future dates are not rejected here: fields such as an identity document's
    ``expiry_date`` are legitimately in the future.
    """
    if not isinstance(value, str):
        return _bad("Date must be an ISO string")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return _bad("Date format is invalid")
    return _ok("Date is valid")


def validate_date_not_future(value: Any) -> ValidationOutcome:
    """An ISO date must be parseable and not in the future."""
    if not isinstance(value, str):
        return _bad("Date must be an ISO string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return _bad("Date format is invalid")
    if parsed > datetime.now(UTC).date():
        return _bad("Date is in the future")
    return _ok("Date is valid")


def validate_statement_period(value: Any) -> ValidationOutcome:
    """A statement period must be a dict with parseable start and end dates."""
    if not isinstance(value, dict):
        return _bad("Statement period must contain start and end dates")
    try:
        datetime.strptime(value["start"], "%Y-%m-%d")
        datetime.strptime(value["end"], "%Y-%m-%d")
    except (KeyError, TypeError, ValueError):
        return _bad("Statement period dates are invalid")
    return _ok("Statement period dates are valid")


def validate_salary_month(value: Any) -> ValidationOutcome:
    """A salary month must be a ``YYYY-MM`` string with a valid month."""
    if not isinstance(value, str):
        return _bad("Salary month must be a string")
    match = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if match is None or not 1 <= int(match.group(2)) <= 12:
        return _bad("Salary month format is invalid")
    return _ok("Salary month is valid")


def validate_tax_year(value: Any) -> ValidationOutcome:
    """A tax year must be a plausible four-digit year."""
    if not isinstance(value, int) or not 1900 <= value <= 2100:
        return _bad("Tax year is not plausible")
    return _ok("Tax year is plausible")


def validate_non_negative_int(value: Any) -> ValidationOutcome:
    """An integer count must be non-negative."""
    if not isinstance(value, int) or value < 0:
        return _bad("Count must be a non-negative integer")
    return _ok("Count is a non-negative integer")


Validator = Callable[[Any], ValidationOutcome]

#: Validators applied to each present field of an analysed document type.
_FIELD_VALIDATORS: dict[AnalyzedDocumentType, dict[str, tuple[str, Validator]]] = {
    AnalyzedDocumentType.BANK_STATEMENT: {
        "account_number": ("account_number", validate_account_number),
        "iban": ("iban_checksum", validate_iban),
        "currency": ("currency", validate_currency),
        "opening_balance": ("balance", validate_balance),
        "closing_balance": ("balance", validate_balance),
        "statement_period": ("period", validate_statement_period),
        "transaction_count": ("non_negative", validate_non_negative_int),
    },
    AnalyzedDocumentType.PAYSLIP: {
        "gross_salary": ("amount", validate_amount),
        "net_salary": ("amount", validate_amount),
        "salary_month": ("salary_month", validate_salary_month),
        "payment_date": ("date_not_future", validate_date_not_future),
    },
    AnalyzedDocumentType.ID_DOCUMENT: {
        "date_of_birth": ("date_not_future", validate_date_not_future),
        "issue_date": ("date", validate_date),
        "expiry_date": ("date", validate_date),
        "document_number": ("document_number", validate_document_number),
    },
    AnalyzedDocumentType.TAX_DOCUMENT: {
        "tax_year": ("tax_year", validate_tax_year),
        "gross_income": ("amount", validate_amount),
        "total_tax": ("amount", validate_amount),
        "currency": ("currency", validate_currency),
    },
    AnalyzedDocumentType.BILATERAL_AGREEMENT: {
        "account_number": ("account_number", validate_account_number),
        "iban": ("iban_checksum", validate_iban),
        "effective_date": ("date", validate_date),
    },
    AnalyzedDocumentType.AUTHORITY_LETTER: {
        "account_number": ("account_number", validate_account_number),
        "iban": ("iban_checksum", validate_iban),
    },
    AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: {
        "account_number": ("account_number", validate_account_number),
        "iban": ("iban_checksum", validate_iban),
        "issue_date": ("date_not_future", validate_date_not_future),
    },
    AnalyzedDocumentType.TRIPARTITE_AGREEMENT: {
        "account_number": ("account_number", validate_account_number),
    },
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: {
        "date": ("date_not_future", validate_date_not_future),
    },
}


def _result(field: str, validator: str, status: str, message: str) -> dict[str, str]:
    """Build a serializable validation result dict."""
    return {"field": field, "validator": validator, "status": status, "message": message}


#: Human-friendly labels used in issue messages for well-known field names.
_FIELD_LABELS: dict[str, str] = {
    "account_holder": "Account holder",
    "account_number": "Account number",
    "iban": "IBAN",
    "bank_name": "Bank name",
    "statement_period": "Statement period",
    "opening_balance": "Opening balance",
    "closing_balance": "Closing balance",
    "total_credits": "Total credits",
    "total_debits": "Total debits",
    "currency": "Currency",
    "transaction_count": "Transaction count",
    "employee_name": "Employee name",
    "employer_name": "Employer name",
    "gross_salary": "Gross salary",
    "net_salary": "Net salary",
    "salary_month": "Salary month",
    "payment_date": "Payment date",
    "employee_id": "Employee id",
    "full_name": "Full name",
    "date_of_birth": "Date of birth",
    "document_number": "Document number",
    "nationality": "Nationality",
    "issue_date": "Issue date",
    "expiry_date": "Expiry date",
    "taxpayer_name": "Taxpayer name",
    "tax_reference_number": "Tax reference number",
    "tax_year": "Tax year",
    "gross_income": "Gross income",
    "total_tax": "Total tax",
    "organization_name": "Organization name",
    "platform_name": "Platform name",
    "transaction_charges": "Transaction charges",
    "effective_date": "Effective date",
    "focal_person_name": "Focal person name",
    "focal_person_designation": "Focal person designation",
    "branch_name": "Branch name",
    "branch_code": "Branch",
    "party_1link": "1-Link party",
    "party_kpitb": "KPITB party",
    "party_subbiller": "Sub-biller party",
    "digitization_intent_confirmed": "Digitization intent confirmation",
    "revenue_services_listed": "Revenue-generating services list",
    "addressee": "Addressee",
    "subject": "Subject",
    "date": "Date",
}


def _label(field: str) -> str:
    """Return the display label for a field name."""
    return _FIELD_LABELS.get(field, field.replace("_", " ").title())


class ValidatorEngine:
    """Runs the configured validators for an analysed document type.

    Every expected field is validated: present fields run their validator
    (``valid`` or ``invalid``) and absent fields are reported as ``missing`` so
    downstream scoring and issue generation can account for gaps.
    """

    def run(self, document_type: AnalyzedDocumentType, fields: dict[str, Any]) -> list[dict[str, str]]:
        """Validate every expected field of a document type against ``fields``.

        Args:
            document_type: Analysed document type selecting the validators.
            fields: Normalized extracted fields.

        Returns:
            A list of validation result dicts, one per expected field.
        """
        expected = EXPECTED_FIELDS.get(document_type, frozenset())
        configured = _FIELD_VALIDATORS.get(document_type, {})
        results: list[dict[str, str]] = []
        for field in sorted(expected):
            if field not in fields or fields[field] is None:
                results.append(
                    _result(field, "required", "missing", f"{_label(field)} missing")
                )
                continue
            validator_name, validator = configured.get(
                field, ("required", validate_required_presence)
            )
            status, message = validator(fields[field])
            results.append(_result(field, validator_name, status, message))
        return results
