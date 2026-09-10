"""Unit tests for the data normalization engine.

Exercises every normalizer in isolation (without a database): IBANs, account
numbers, names, bank aliases, CNICs, dates in multiple formats, statement
periods, salary months, branch abbreviations, vendors, whitespace/unicode
handling, idempotency and the field-to-normalizer registry with its general-text
fallback. The eligibility predicate and the single-field service method round
out the engine coverage.
"""

import pytest

from app.normalization.constants import (
    DEFAULT_NORMALIZER,
    FIELD_NORMALIZERS,
    NormalizationOutcome,
)
from app.normalization.normalizers import (
    AccountNumberNormalizer,
    BankNameNormalizer,
    BranchNameNormalizer,
    CnicNormalizer,
    DateNormalizer,
    GeneralTextNormalizer,
    IbanNormalizer,
    NormalizerRegistry,
    SalaryMonthNormalizer,
    StatementPeriodNormalizer,
    TitleNormalizer,
    VendorNormalizer,
    clean_text,
)
from app.normalization.validators import is_verified_for_normalization

REGISTRY = NormalizerRegistry()


# --- General text cleanup ----------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  hello   world \n", "hello world"),
        ("a\x00b", "ab"),
        ("\ufeffBOM", "BOM"),
        ("ｆｕｌｌ　ｗｉｄｔｈ", "full width"),
        ("\ttabbed\ttext ", "tabbed text"),
    ],
)
def test_clean_text(value, expected):
    assert clean_text(value) == expected


def test_clean_text_preserves_case():
    assert clean_text("Ahmad Raza") == "Ahmad Raza"


def test_general_text_keeps_case():
    normalizer = GeneralTextNormalizer()
    assert normalizer.normalize("  MIXED Case  Value ") == "MIXED Case Value"


def test_title_normalizer_uppercases_and_collapses():
    assert TitleNormalizer().normalize("  ahmad   raza ") == "AHMAD RAZA"


# --- IBAN --------------------------------------------------------------------


def test_iban_normalizer_strips_formatting_and_uppercases():
    normalizer = IbanNormalizer()
    assert (
        normalizer.normalize("pk36 scbl 0000 0011 2345 6702")
        == "PK36SCBL0000001123456702"
    )


def test_iban_normalizer_keeps_canonical_unchanged():
    normalizer = IbanNormalizer()
    assert normalizer.normalize("PK36SCBL0000001123456702") == "PK36SCBL0000001123456702"


def test_iban_normalizer_raises_on_invalid_structure():
    with pytest.raises(ValueError, match="Invalid IBAN"):
        IbanNormalizer().normalize("not-an-iban")


def test_iban_normalizer_raises_on_too_long():
    with pytest.raises(ValueError):
        IbanNormalizer().normalize("PK" + "0" * 40)


def test_iban_normalizer_is_idempotent():
    normalizer = IbanNormalizer()
    once = normalizer.normalize("pk36-scbl-0000-0011-2345-6702")
    assert normalizer.normalize(once) == once


# --- Account numbers ---------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0011-2345-6702", "001123456702"),
        ("0011 2345 6702", "001123456702"),
        ("0011.2345.6702", "001123456702"),
        ("0011/2345/6702", "001123456702"),
        ("PK36", "PK36"),
        ("0011-2345-6702 ", "001123456702"),
    ],
)
def test_account_number_normalizer(value, expected):
    assert AccountNumberNormalizer().normalize(value) == expected


def test_account_number_keeps_leading_zeros():
    assert AccountNumberNormalizer().normalize("0012345") == "0012345"


# --- Names -------------------------------------------------------------------


def test_title_normalizer_is_idempotent():
    normalizer = TitleNormalizer()
    once = normalizer.normalize("  ahmad   raza ")
    assert normalizer.normalize(once) == once


# --- Bank names --------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HBL", "HABIB BANK LIMITED"),
        ("Habib Bank", "HABIB BANK LIMITED"),
        ("  habib  bank  ltd ", "HABIB BANK LIMITED"),
        ("UBL", "UNITED BANK LIMITED"),
        ("Meezan Bank", "MEEZAN BANK LIMITED"),
        ("First Micro Bank", "FIRST MICRO BANK"),
    ],
)
def test_bank_name_normalizer_resolves_aliases(value, expected):
    assert BankNameNormalizer().normalize(value) == expected


# --- CNIC --------------------------------------------------------------------


def test_cnic_normalizer_formats_thirteen_digits():
    assert CnicNormalizer().normalize("3520212345671") == "35202-1234567-1"


def test_cnic_normalizer_accepts_formatted_input():
    assert CnicNormalizer().normalize("35202-1234567-1") == "35202-1234567-1"


def test_cnic_normalizer_passes_non_digit_values_through_general_text():
    assert CnicNormalizer().normalize("  E-1234567 ") == "E-1234567"


# --- Dates -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-01-31", "2024-01-31"),
        ("31/01/2024", "2024-01-31"),
        ("31-01-2024", "2024-01-31"),
        ("31 Jan 2024", "2024-01-31"),
        ("31 January 2024", "2024-01-31"),
        ("31 Jan, 2024", "2024-01-31"),
        ("31 January, 2024", "2024-01-31"),
        ("Jan 31 2024", "2024-01-31"),
        ("January 31 2024", "2024-01-31"),
        ("Jan 31, 2024", "2024-01-31"),
        ("January 31, 2024", "2024-01-31"),
        ("2024/01/31", "2024-01-31"),
        ("  31/01/2024  ", "2024-01-31"),
    ],
)
def test_date_normalizer(value, expected):
    assert DateNormalizer().normalize(value) == expected


def test_date_normalizer_raises_on_unparseable():
    with pytest.raises(ValueError, match="Could not parse date"):
        DateNormalizer().normalize("thirty-first")


def test_date_normalizer_is_idempotent():
    normalizer = DateNormalizer()
    once = normalizer.normalize("31/01/2024")
    assert normalizer.normalize(once) == once


# --- Statement periods -------------------------------------------------------


def test_statement_period_parses_text_range():
    assert (
        StatementPeriodNormalizer().normalize("01/01/2024 - 31/01/2024")
        == "2024-01-01 - 2024-01-31"
    )


def test_statement_period_parses_dictionary_string():
    period = "{'start': '2024-01-01', 'end': '2024-01-31'}"
    assert StatementPeriodNormalizer().normalize(period) == "2024-01-01 - 2024-01-31"


def test_statement_period_raises_on_missing_endpoint():
    with pytest.raises(ValueError, match="Could not parse statement period"):
        StatementPeriodNormalizer().normalize("01/01/2024")


# --- Salary months -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-01", "2024-01"),
        ("01/2024", "2024-01"),
        ("2024/01", "2024-01"),
        ("Jan 2024", "2024-01"),
        ("January 2024", "2024-01"),
    ],
)
def test_salary_month_normalizer(value, expected):
    assert SalaryMonthNormalizer().normalize(value) == expected


def test_salary_month_raises_on_full_date():
    with pytest.raises(ValueError, match="Could not parse salary month"):
        SalaryMonthNormalizer().normalize("2024-01-31")


# --- Branch names ------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("M. TOWN BR ISB", "Model Town Branch Islamabad"),
        ("h.o karachi", "Head Office Karachi"),
        ("saddar", "Saddar"),
        ("  lahore  main ", "Lahore Main"),
    ],
)
def test_branch_name_normalizer(value, expected):
    assert BranchNameNormalizer().normalize(value) == expected


# --- Vendors -----------------------------------------------------------------


def test_vendor_normalizer_uppercases():
    assert VendorNormalizer().normalize("  Gulf Trading  Co ") == "GULF TRADING CO"


# --- Registry ----------------------------------------------------------------


def test_registry_resolves_known_fields():
    assert FIELD_NORMALIZERS["iban"] == "iban"
    assert REGISTRY.for_field("iban").identifier == "iban"
    assert REGISTRY.for_field("account_holder").identifier == "title"
    assert REGISTRY.for_field("statement_period").identifier == "statement_period"
    assert REGISTRY.for_field("bank_name").identifier == "bank_name"


def test_registry_falls_back_to_general_text_for_unknown_fields():
    assert DEFAULT_NORMALIZER == "general_text"
    normalizer = REGISTRY.for_field("some_unknown_field")
    assert normalizer.identifier == "general_text"


def test_registry_normalize_dispatch_by_field_name():
    assert REGISTRY.normalize("iban", "pk36 scbl 0000 0011 2345 6702") == (
        "PK36SCBL0000001123456702"
    )


def test_registry_get_unknown_identifier_raises_key_error():
    with pytest.raises(KeyError):
        REGISTRY.get("does-not-exist")


# --- Eligibility predicate ---------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("VERIFIED", True),
        ("CORRECTED", True),
        ("AUTO_VERIFIED", True),
        ("PENDING_REVIEW", False),
        ("CANNOT_VERIFY", False),
        (None, True),
    ],
)
def test_is_verified_for_normalization(status, expected):
    assert is_verified_for_normalization(status) is expected


# --- Single-field service method ---------------------------------------------


def test_normalize_field_returns_normalized_item():
    from app.normalization.services import NormalizationService

    service = NormalizationService(None)
    item = service.normalize_field(field_name="iban", value="pk36 scbl 0000 0011 23")
    assert item.status is NormalizationOutcome.NORMALIZED
    assert item.normalized_value == "PK36SCBL0000001123"
    assert item.normalizer == "iban"


def test_normalize_field_skips_unverified_field():
    from app.normalization.services import NormalizationService

    service = NormalizationService(None)
    item = service.normalize_field(
        field_name="iban",
        value="PK36SCBL0000",
        verification_status="PENDING_REVIEW",
    )
    assert item.status is NormalizationOutcome.SKIPPED
    assert item.reason == "not verified: PENDING_REVIEW"


def test_normalize_field_skips_empty_value():
    from app.normalization.services import NormalizationService

    service = NormalizationService(None)
    item = service.normalize_field(field_name="iban", value="   ")
    assert item.status is NormalizationOutcome.SKIPPED
    assert item.reason == "empty value"


def test_normalize_field_reports_failed_value():
    from app.normalization.services import NormalizationService

    service = NormalizationService(None)
    item = service.normalize_field(field_name="iban", value="not-an-iban")
    assert item.status is NormalizationOutcome.FAILED
    assert "Invalid IBAN" in item.reason
