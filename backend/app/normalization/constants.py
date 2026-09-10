"""Configuration for the data normalization module.

Centralizes the normalization statuses, the per-field outcome vocabulary, the
field-to-normalizer mapping, the alias tables and the accepted date formats.
Everything the normalizers and the service need to know is data in this module,
so adding a bank, expanding a branch abbreviation or accepting a new date format
never requires touching business logic.
"""

from enum import StrEnum

#: Version of the normalization logic. Bumped whenever a normalizer or the
#: field mapping changes so stored ``normalized_value`` columns can be traced to
#: the exact logic that produced them.
NORMALIZATION_VERSION: str = "1.0.0"


class NormalizationStatus(StrEnum):
    """Application-level outcome of a normalization run."""

    READY_FOR_BUSINESS_VALIDATION = "READY_FOR_BUSINESS_VALIDATION"


class NormalizationOutcome(StrEnum):
    """Per-field outcome of a normalization run."""

    NORMALIZED = "NORMALIZED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


# -- Verification statuses that block normalization ---------------------------
#: Fields in these states are not considered verified and must be skipped: a
#: pending field may still change after human review and a halted field has no
#: trustworthy value to canonicalize.
SKIPPED_VERIFICATION_STATUSES: frozenset[str] = frozenset(
    {"PENDING_REVIEW", "CANNOT_VERIFY"}
)


# -- Configurable alias tables ------------------------------------------------
#: Canonical bank names. Keys are the already-normalized (trimmed, collapsed and
#: uppercased) input forms; values are the canonical legal entity name.
BANK_ALIASES: dict[str, str] = {
    "HBL": "HABIB BANK LIMITED",
    "HABIB BANK": "HABIB BANK LIMITED",
    "HABIB BANK LTD": "HABIB BANK LIMITED",
    "HABIB BANK LIMITED": "HABIB BANK LIMITED",
    "UBL": "UNITED BANK LIMITED",
    "UNITED BANK": "UNITED BANK LIMITED",
    "UNITED BANK LTD": "UNITED BANK LIMITED",
    "UNITED BANK LIMITED": "UNITED BANK LIMITED",
    "MCB": "MCB BANK LIMITED",
    "MCB BANK": "MCB BANK LIMITED",
    "MCB BANK LIMITED": "MCB BANK LIMITED",
    "ABL": "ALLIED BANK LIMITED",
    "ALLIED BANK": "ALLIED BANK LIMITED",
    "ALLIED BANK LTD": "ALLIED BANK LIMITED",
    "ALLIED BANK LIMITED": "ALLIED BANK LIMITED",
    "MEEZAN BANK": "MEEZAN BANK LIMITED",
    "MEEZAN BANK LTD": "MEEZAN BANK LIMITED",
    "MEEZAN BANK LIMITED": "MEEZAN BANK LIMITED",
    "NBP": "NATIONAL BANK OF PAKISTAN",
    "NATIONAL BANK": "NATIONAL BANK OF PAKISTAN",
    "NATIONAL BANK OF PAKISTAN": "NATIONAL BANK OF PAKISTAN",
    "BOP": "BANK OF PUNJAB",
    "BANK OF PUNJAB": "BANK OF PUNJAB",
    "BANK ALFALAH": "BANK ALFALAH LIMITED",
    "BANK ALFALAH LTD": "BANK ALFALAH LIMITED",
    "BANK ALFALAH LIMITED": "BANK ALFALAH LIMITED",
}

#: Branch abbreviation expansions. Keys are normalized (collapsed, uppercased)
#: token forms; values are the expanded words inserted in place.
BRANCH_ALIASES: dict[str, str] = {
    "BR": "BRANCH",
    "BRNCH": "BRANCH",
    "B/O": "BRANCH OFFICE",
    "H.O": "HEAD OFFICE",
    "HO": "HEAD OFFICE",
    "HEAD OFFICE": "HEAD OFFICE",
    "ISB": "ISLAMABAD",
    "LHR": "LAHORE",
    "KHI": "KARACHI",
    "KARACHI": "KARACHI",
    "LAHORE": "LAHORE",
    "ISLAMABAD": "ISLAMABAD",
    "M. TOWN": "MODEL TOWN",
    "MODEL TOWN": "MODEL TOWN",
    "SADDAR": "SADDAR",
    "GUJRAWALA": "GUJRANWALA",
}

#: Accepted date formats in ``strptime`` notation, tried in order. The ambiguous
#: slash format is resolved day-first to match the extraction engine's ``_parse_date``.
DATE_FORMATS: list[str] = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
    "%d %b, %Y",
    "%d %B, %Y",
    "%b %d, %Y",
    "%B %d, %Y",
]


# -- Field-to-normalizer mapping ----------------------------------------------
#: Maps every known field name onto its normalizer identifier. Fields without an
#: entry fall back to the general text normalizer.
FIELD_NORMALIZERS: dict[str, str] = {
    "iban": "iban",
    "account_number": "account_number",
    "account_holder": "title",
    "employee_name": "title",
    "employer_name": "title",
    "full_name": "title",
    "taxpayer_name": "title",
    "bank_name": "bank_name",
    "document_number": "cnic",
    "employee_id": "cnic",
    "tax_reference_number": "cnic",
    "date_of_birth": "date",
    "issue_date": "date",
    "expiry_date": "date",
    "payment_date": "date",
    "statement_period": "statement_period",
    "salary_month": "salary_month",
    "branch": "branch",
    "branch_name": "branch",
    "vendor_name": "vendor",
    "payee": "vendor",
}

#: Normalizer used when a field has no dedicated normalizer.
DEFAULT_NORMALIZER: str = "general_text"


# -- Audit action identifiers -------------------------------------------------
ACTION_NORMALIZED: str = "normalization.completed"
