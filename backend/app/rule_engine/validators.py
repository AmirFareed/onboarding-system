"""Shared predicates for the business rule engine format rules.

The canonical-shape checks reused by the format rules live here (or are
delegated to the normalization module's validators so both modules enforce the
exact same formats). Every predicate is a pure function of a value so the rules
stay trivially testable.
"""

import re

#: Monetary amount shape: digits (plain or thousands-separated) with an
#: optional up-to-two-decimal fraction. Matches the cleaned values the
#: normalization module stores (e.g. ``1250.5`` or ``1,250.50``).
AMOUNT_PATTERN: re.Pattern[str] = re.compile(
    r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?$"
)

#: Bank account number shape: 6 to 20 letters or digits.
ACCOUNT_NUMBER_PATTERN: re.Pattern[str] = re.compile(r"^[A-Z0-9]{6,20}$")

#: Placeholder account titles that never satisfy the policy rule.
PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(
    r"^(NOT PROVIDED|N/A|NA|NONE|X+|UNKNOWN|TBD)$"
)


def is_canonical_amount(value: str) -> bool:
    """Return whether ``value`` matches the canonical monetary amount shape."""
    return AMOUNT_PATTERN.fullmatch(value) is not None


def is_valid_account_number(value: str) -> bool:
    """Return whether ``value`` matches the account number shape."""
    return ACCOUNT_NUMBER_PATTERN.fullmatch(value) is not None


def is_placeholder(value: str) -> bool:
    """Return whether ``value`` is a placeholder account title."""
    return PLACEHOLDER_PATTERN.fullmatch(value.upper().strip()) is not None


def is_positive_integer(value: str) -> bool:
    """Return whether ``value`` is a positive integer."""
    if not value:
        return False
    try:
        return int(value) > 0
    except ValueError:
        return False
