"""Reusable validators and predicates for the data normalization module.

The normalizers share two concerns that belong here rather than in each class:
deciding whether a field is eligible for normalization, and verifying that a
canonical output actually satisfies its format contract. Keeping them in one
place guarantees every normalizer enforces exactly the same rules.
"""

import re

from app.normalization.constants import SKIPPED_VERIFICATION_STATUSES

#: Canonical CNIC shape: five digits, hyphen, seven digits, hyphen, one digit.
CNIC_PATTERN: re.Pattern[str] = re.compile(r"^\d{5}-\d{7}-\d$")

#: Canonical IBAN shape: two letters, two digits, then letters/digits to a
#: maximum length of 34. Length is re-checked on the value itself.
IBAN_PATTERN: re.Pattern[str] = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")

#: Canonical date shape: ``YYYY-MM-DD``.
ISO_DATE_PATTERN: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Canonical year-month shape: ``YYYY-MM``.
ISO_YEAR_MONTH_PATTERN: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}$")


def is_verified_for_normalization(verification_status: str) -> bool:
    """Return whether a field in ``verification_status`` may be normalized.

    Only fields whose value is trustworthy are canonicalized: pending fields may
    still change after human review and halted fields have no dependable value.
    """
    return verification_status not in SKIPPED_VERIFICATION_STATUSES


def is_canonical_cnic(value: str) -> bool:
    """Return whether ``value`` already matches the canonical CNIC shape."""
    return CNIC_PATTERN.fullmatch(value) is not None


def is_canonical_iban(value: str) -> bool:
    """Return whether ``value`` already matches the canonical IBAN shape."""
    if IBAN_PATTERN.fullmatch(value) is None:
        return False
    return len(value) <= 34


def is_canonical_iso_date(value: str) -> bool:
    """Return whether ``value`` already matches the canonical date shape."""
    return ISO_DATE_PATTERN.fullmatch(value) is not None


def is_canonical_iso_year_month(value: str) -> bool:
    """Return whether ``value`` already matches the canonical year-month shape."""
    return ISO_YEAR_MONTH_PATTERN.fullmatch(value) is not None
