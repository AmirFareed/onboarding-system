"""Value normalizers for the data normalization module.

Each normalizer is a small, independent class that turns one class of extracted
value into a deterministic canonical form. Normalizers are pure functions of
their input: they raise ``ValueError`` when the input is not the shape they
expect and otherwise return a string. They never touch the database or make
business decisions, so they can be unit tested in isolation.

The ``NormalizerRegistry`` maps every known field name onto its normalizer and
falls back to the general text normalizer for anything else. The mapping lives
in ``constants.FIELD_NORMALIZERS`` so wiring a new field is a data change.
"""

from __future__ import annotations

import ast
import re
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime

from app.normalization.constants import (
    BANK_ALIASES,
    BRANCH_ALIASES,
    DATE_FORMATS,
    DEFAULT_NORMALIZER,
    FIELD_NORMALIZERS,
)
from app.normalization.validators import (
    is_canonical_iban,
    is_canonical_iso_date,
    is_canonical_iso_year_month,
)

#: Control characters (category starting with ``C``) removed from text values.
_CONTROL_CHARS = str.maketrans(
    {
        code: None
        for code in range(0x110000)
        if unicodedata.category(chr(code))[0] == "C"
    }
)


def clean_text(value: str) -> str:
    """Strip control characters and collapse whitespace in ``value``.

    Applies Unicode NFKC normalization first so compatible characters
    (full-width digits, ligatures) resolve to their canonical forms, then
    collapses any run of whitespace to a single space (including tabs and
    newlines, which act as separators) and drops the remaining control
    characters.
    """
    normalized = unicodedata.normalize("NFKC", value)
    collapsed = " ".join(normalized.split())
    return collapsed.translate(_CONTROL_CHARS)


def _parse_date(value: str) -> datetime | None:
    """Parse ``value`` with the configured date formats in order.

    Returns ``None`` when no format matches. The date is not normalizable when
    this fails, which the caller turns into a ``ValueError``.
    """
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


class BaseNormalizer(ABC):
    """Base class for value normalizers.

    Attributes:
        identifier: Stable name of the normalizer, stored per field in the
            normalization result and referenced by the field mapping.
    """

    identifier: str = "base"

    @abstractmethod
    def normalize(self, value: str) -> str:
        """Return the canonical form of ``value``.

        Raises:
            ValueError: When the value is not of the shape this normalizer
                expects, so the value cannot be canonicalized.
        """


class GeneralTextNormalizer(BaseNormalizer):
    """Fallback: light cleanup that changes nothing semantically.

    Strips control characters, collapses whitespace and applies NFKC
    normalization. Case is deliberately preserved because general text is not
    required to match any vocabulary.
    """

    identifier = "general_text"

    def normalize(self, value: str) -> str:
        return clean_text(value)


class TitleNormalizer(BaseNormalizer):
    """Person or organisation names, uppercased."""

    identifier = "title"

    def normalize(self, value: str) -> str:
        return clean_text(value).upper()


class IbanNormalizer(BaseNormalizer):
    """International bank account numbers.

    Strips formatting characters, uppercases, and validates the resulting
    structure. A value that cannot be an IBAN fails loudly instead of producing
    a silently wrong canonical form.
    """

    identifier = "iban"

    def normalize(self, value: str) -> str:
        cleaned = re.sub(r"[\s\-]", "", value).upper()
        if not is_canonical_iban(cleaned):
            raise ValueError(f"Invalid IBAN structure: {value!r}")
        return cleaned


class AccountNumberNormalizer(BaseNormalizer):
    """Bank account numbers.

    Removes common formatting characters and uppercases any letters. Leading
    zeros are significant in account numbers and are always preserved.
    """

    identifier = "account_number"

    def normalize(self, value: str) -> str:
        return re.sub(r"[\s\-/.]", "", value).upper()


class CnicNormalizer(BaseNormalizer):
    """National identity card numbers.

    A 13-digit value is formatted as ``XXXXX-XXXXXXX-X``; anything else (for
    example a passport number) is passed through the general text normalizer so
    it is cleaned without being forced into an identity-card shape.
    """

    identifier = "cnic"

    def normalize(self, value: str) -> str:
        digits_only = re.sub(r"[\s\-]", "", value)
        if digits_only.isdigit() and len(digits_only) == 13:
            return f"{digits_only[:5]}-{digits_only[5:12]}-{digits_only[12:]}"
        return GeneralTextNormalizer().normalize(value)


class BankNameNormalizer(BaseNormalizer):
    """Bank names resolved to their canonical legal entity name.

    The input is cleaned and uppercased, then looked up in ``BANK_ALIASES`` so
    abbreviations and variant spellings collapse onto one canonical name.
    Unknown banks keep their cleaned, uppercased name.
    """

    identifier = "bank_name"

    def normalize(self, value: str) -> str:
        cleaned = clean_text(value).upper()
        return BANK_ALIASES.get(cleaned, cleaned)


class DateNormalizer(BaseNormalizer):
    """Dates normalised to ``YYYY-MM-DD``.

    Accepts every format in ``DATE_FORMATS``; values that are already in the
    canonical form pass through unchanged, which keeps the normalizer idempotent.
    """

    identifier = "date"

    def normalize(self, value: str) -> str:
        cleaned = clean_text(value)
        if is_canonical_iso_date(cleaned):
            return cleaned
        parsed = _parse_date(cleaned)
        if parsed is None:
            raise ValueError(f"Could not parse date: {value!r}")
        return parsed.strftime("%Y-%m-%d")


class StatementPeriodNormalizer(BaseNormalizer):
    """Statement periods normalised to ``YYYY-MM-DD - YYYY-MM-DD``.

    Handles both raw range strings (``01/01/2024 - 31/01/2024``) and the stored
    dictionary string produced by the extraction engine
    (``"{'start': ..., 'end': ...}"``).
    """

    identifier = "statement_period"

    def normalize(self, value: str) -> str:
        cleaned = clean_text(value)
        if cleaned.startswith("{"):
            start, end = self._extract_dict_range(cleaned)
        else:
            start, end = self._extract_text_range(cleaned)
        start_iso = self._to_iso(start)
        end_iso = self._to_iso(end)
        return f"{start_iso} - {end_iso}"

    @staticmethod
    def _extract_dict_range(value: str) -> tuple[str, str]:
        try:
            payload = ast.literal_eval(value)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"Could not parse statement period: {value!r}") from exc
        start = payload.get("start") or payload.get("start_date")
        end = payload.get("end") or payload.get("end_date")
        if not start or not end:
            raise ValueError(f"Statement period missing start/end: {value!r}")
        return str(start), str(end)

    @staticmethod
    def _extract_text_range(value: str) -> tuple[str, str]:
        parts = re.split(r"\s+(?:-|–|—|to)\s+", value)
        if len(parts) != 2:
            raise ValueError(f"Could not parse statement period: {value!r}")
        return parts[0], parts[1]

    @staticmethod
    def _to_iso(value: str) -> str:
        parsed = _parse_date(value)
        if parsed is None:
            raise ValueError(f"Could not parse statement period endpoint: {value!r}")
        return parsed.strftime("%Y-%m-%d")


class SalaryMonthNormalizer(BaseNormalizer):
    """Salary months normalised to ``YYYY-MM``.

    Accepts ``YYYY-MM`` plus the month-level formats commonly produced by the
    extraction engine (``January 2024``, ``Jan 2024``, ``01/2024``).
    """

    identifier = "salary_month"

    _FORMATS: list[str] = [
        "%Y-%m",
        "%m/%Y",
        "%Y/%m",
        "%b %Y",
        "%B %Y",
        "%b-%Y",
        "%B-%Y",
    ]

    def normalize(self, value: str) -> str:
        cleaned = clean_text(value)
        if is_canonical_iso_year_month(cleaned):
            return cleaned
        for fmt in self._FORMATS:
            try:
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m")
            except ValueError:
                continue
        raise ValueError(f"Could not parse salary month: {value!r}")


class BranchNameNormalizer(BaseNormalizer):
    """Branch names: abbreviations expanded and words title-cased.

    Abbreviations are expanded via ``BRANCH_ALIASES`` (multi-word aliases first,
    then token by token) and the result is title-cased, so ``M. TOWN BR ISB``
    becomes ``Model Town Branch Islamabad``.
    """

    identifier = "branch"

    def normalize(self, value: str) -> str:
        upper = clean_text(value).upper()
        phrase_aliases = sorted(
            (key for key in BRANCH_ALIASES if " " in key or "." in key),
            key=len,
            reverse=True,
        )
        for alias in phrase_aliases:
            if alias in upper:
                upper = upper.replace(alias, BRANCH_ALIASES[alias])
        expanded = " ".join(BRANCH_ALIASES.get(token, token) for token in upper.split())
        return expanded.title()


class VendorNormalizer(BaseNormalizer):
    """Payee/vendor names, uppercased."""

    identifier = "vendor"

    def normalize(self, value: str) -> str:
        return clean_text(value).upper()


class NormalizerRegistry:
    """Registry mapping field names onto normalizer instances.

    Wires the ``FIELD_NORMALIZERS`` mapping to the concrete normalizer classes,
    falling back to the general text normalizer for unmapped fields.
    """

    def __init__(self, normalizers: Iterable[BaseNormalizer] | None = None) -> None:
        self._normalizers: dict[str, BaseNormalizer] = {}
        for normalizer in normalizers or self._default_normalizers():
            self._normalizers[normalizer.identifier] = normalizer

    @staticmethod
    def _default_normalizers() -> list[BaseNormalizer]:
        return [
            GeneralTextNormalizer(),
            TitleNormalizer(),
            IbanNormalizer(),
            AccountNumberNormalizer(),
            CnicNormalizer(),
            BankNameNormalizer(),
            DateNormalizer(),
            StatementPeriodNormalizer(),
            SalaryMonthNormalizer(),
            BranchNameNormalizer(),
            VendorNormalizer(),
        ]

    def get(self, identifier: str) -> BaseNormalizer:
        """Return the normalizer registered under ``identifier``."""
        return self._normalizers[identifier]

    def for_field(self, field_name: str) -> BaseNormalizer:
        """Return the normalizer that handles ``field_name``."""
        identifier = FIELD_NORMALIZERS.get(field_name, DEFAULT_NORMALIZER)
        return self.get(identifier)

    def normalize(self, field_name: str, value: str) -> str:
        """Normalize ``value`` with the normalizer for ``field_name``."""
        return self.for_field(field_name).normalize(value)
