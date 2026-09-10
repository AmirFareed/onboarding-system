"""Tests for the feedback module's pure helpers.

The validator layer carries no I/O: filter validation, datetime
normalization, the canonical 14-field serialization and the CSV builder are
exercised in isolation here. The module is read-mostly, so these helpers are
the only place where the aggregation and export logic can be unit-tested
without a database.
"""

import csv
import io
from datetime import datetime, timezone

import pytest

from app.database.models.enums import DocumentType
from app.database.models.feedback_dataset import FeedbackEntry as FeedbackEntryModel
from app.feedback.constants import (
    CSV_COLUMNS,
    UNKNOWN_DOCUMENT_TYPE,
    UNKNOWN_REVIEWER,
)
from app.feedback.exceptions import InvalidFilter
from app.feedback.schemas import FeedbackFilters
from app.feedback.validators import (
    build_csv,
    document_type_label,
    ensure_aware,
    entry_to_dict,
    to_repository_filters,
    validate_filters,
)


# --- Filter validation -------------------------------------------------------


def test_empty_filters_are_valid():
    filters = FeedbackFilters()
    assert validate_filters(filters) is filters


def test_all_filters_are_valid():
    filters = FeedbackFilters(
        application_id=3,
        reviewer="alice",
        document_type=DocumentType.ONE_LINK_LETTER,
        field_name="amount",
        decision="CORRECT",
        date_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        date_to=datetime(2026, 12, 31, tzinfo=timezone.utc),
        min_confidence=0.5,
    )
    assert validate_filters(filters) is filters


def test_inverted_date_range_is_rejected():
    filters = FeedbackFilters(
        date_from=datetime(2026, 12, 31, tzinfo=timezone.utc),
        date_to=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(InvalidFilter):
        validate_filters(filters)


def test_equal_date_range_is_accepted():
    instant = datetime(2026, 6, 1, tzinfo=timezone.utc)
    filters = FeedbackFilters(date_from=instant, date_to=instant)
    assert validate_filters(filters) is filters


def test_unknown_decision_is_rejected():
    filters = FeedbackFilters(decision="BOGUS")
    with pytest.raises(InvalidFilter, match="unknown decision"):
        validate_filters(filters)


def test_known_decisions_are_accepted():
    for decision in ("APPROVE", "CORRECT", "REJECT", "CORRECTED"):
        assert validate_filters(FeedbackFilters(decision=decision)) is not None


def test_repository_filters_roundtrip():
    filters = FeedbackFilters(
        application_id=3,
        reviewer="alice",
        document_type=DocumentType.ONE_LINK_LETTER,
        field_name="amount",
        decision="CORRECT",
        date_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        date_to=datetime(2026, 12, 31, tzinfo=timezone.utc),
        min_confidence=0.5,
    )
    mapping = to_repository_filters(filters)
    assert mapping["application_id"] == 3
    assert mapping["reviewer"] == "alice"
    assert mapping["document_type"] is DocumentType.ONE_LINK_LETTER
    assert mapping["field_name"] == "amount"
    assert mapping["decision"] == "CORRECT"
    assert mapping["date_from"] == filters.date_from
    assert mapping["date_to"] == filters.date_to
    assert mapping["min_confidence"] == 0.5


# --- Datetime normalization --------------------------------------------------


def test_ensure_aware_keeps_aware_datetime():
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert ensure_aware(instant) is instant


def test_ensure_aware_assumes_utc_for_naive_datetime():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = ensure_aware(naive)
    assert aware.tzinfo == timezone.utc
    assert aware.hour == 12


# --- Canonical serialization -------------------------------------------------


def _sample_entry() -> FeedbackEntryModel:
    return FeedbackEntryModel(
        id=7,
        application_id=1,
        document_id=2,
        ocr_result_id=3,
        field_name="amount",
        ocr_value="1,000",
        normalized_value="1000.00",
        human_value="1000.00",
        confidence_score=0.9,
        confidence_source="regex",
        correction_reason="comma was misread",
        reviewer="alice",
        decision="CORRECT",
        origin="FINAL_HUMAN_REVIEW",
        recorded_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def test_entry_to_dict_exposes_all_14_fields():
    record = entry_to_dict(_sample_entry())
    assert set(record) == set(CSV_COLUMNS)
    assert record["id"] == 7
    assert record["application_id"] == 1
    assert record["document_id"] == 2
    assert record["ocr_result_id"] == 3
    assert record["field_name"] == "amount"
    assert record["original_ocr_value"] == "1,000"
    assert record["normalized_value"] == "1000.00"
    assert record["human_corrected_value"] == "1000.00"
    assert record["confidence_score"] == 0.9
    assert record["confidence_source"] == "regex"
    assert record["correction_reason"] == "comma was misread"
    assert record["reviewer"] == "alice"
    assert record["decision"] == "CORRECT"
    assert record["origin"] == "FINAL_HUMAN_REVIEW"


def test_entry_to_dict_keeps_nullable_fields_none():
    record = entry_to_dict(
        FeedbackEntryModel(
            id=1,
            application_id=None,
            field_name="amount",
            human_value="1000",
        )
    )
    assert record["document_id"] is None
    assert record["ocr_result_id"] is None
    assert record["original_ocr_value"] is None
    assert record["confidence_score"] is None
    assert record["reviewer"] is None
    assert record["decision"] is None
    assert record["origin"] is None


# --- CSV builder -------------------------------------------------------------


def test_build_csv_emits_header_and_rows():
    rows = [
        entry_to_dict(_sample_entry()),
        entry_to_dict(
            FeedbackEntryModel(
                id=8,
                field_name="iban",
                human_value="DE89",
                ocr_value="DE89",
            )
        ),
    ]
    payload = build_csv(rows, CSV_COLUMNS)
    reader = csv.DictReader(payload.splitlines())
    assert reader.fieldnames == list(CSV_COLUMNS)
    parsed = list(reader)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "7"
    assert parsed[0]["field_name"] == "amount"
    assert parsed[0]["reviewer"] == "alice"


def test_build_csv_escapes_special_characters():
    rows = [
        {
            "id": 1,
            "field_name": "amount",
            "original_ocr_value": '1,000 "confirmed"',
            "human_corrected_value": "1000\nline2",
        }
    ]
    payload = build_csv(rows, CSV_COLUMNS)
    parsed = list(csv.DictReader(io.StringIO(payload)))
    assert parsed[0]["original_ocr_value"] == '1,000 "confirmed"'
    assert parsed[0]["human_corrected_value"] == "1000\nline2"


def test_build_csv_empty_rows_produces_header_only():
    payload = build_csv([], CSV_COLUMNS)
    assert payload.strip() == ",".join(CSV_COLUMNS)


# --- Document type label -----------------------------------------------------


def test_document_type_label_returns_value():
    assert document_type_label(DocumentType.ONE_LINK_LETTER) == "ONE_LINK_LETTER"


def test_document_type_label_unknown():
    assert document_type_label(None) == UNKNOWN_DOCUMENT_TYPE


def test_unknown_reviewer_constant():
    assert UNKNOWN_REVIEWER == "UNKNOWN"
