"""Tests for the continuous learning curation helpers.

Unit tests exercise the pure validation, record-building, hashing and
completeness helpers in ``app.continuous_learning.validators`` using transient
``FeedbackEntry`` objects, so no database is required.
"""

from datetime import datetime, timezone

from app.continuous_learning.constants import CSV_COLUMNS
from app.continuous_learning.validators import (
    INVALID_CONFIDENCE_SCORE,
    INVALID_DECISION,
    INVALID_MISSING_APPLICATION_ID,
    INVALID_MISSING_FIELD_NAME,
    INVALID_MISSING_HUMAN_VALUE,
    INVALID_MISSING_OCR_VALUE,
    build_record,
    canonical_records_json,
    compute_completeness,
    confidence_bucket,
    duplicate_signature,
    reviewer_label,
    validation_issue,
)
from app.database.models.enums import DocumentType
from app.database.models.feedback_dataset import FeedbackEntry


def sample(**overrides) -> FeedbackEntry:
    """Build a feedback entry that passes every curation rule by default."""
    values = {
        "id": 1,
        "application_id": 10,
        "document_id": 20,
        "field_name": "account_number",
        "ocr_value": "1234567890",
        "human_value": "9999999999",
        "confidence_score": 0.85,
        "decision": "CORRECT",
        "recorded_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return FeedbackEntry(**values)


def test_valid_record_has_no_issue():
    assert validation_issue(sample()) is None


def test_missing_application_id_rejected():
    assert validation_issue(sample(application_id=None)) == INVALID_MISSING_APPLICATION_ID


def test_empty_application_id_rejected():
    assert validation_issue(sample(application_id=0)) is None


def test_missing_field_name_rejected():
    assert validation_issue(sample(field_name="")) == INVALID_MISSING_FIELD_NAME
    assert validation_issue(sample(field_name="   ")) == INVALID_MISSING_FIELD_NAME
    assert validation_issue(sample(field_name=None)) == INVALID_MISSING_FIELD_NAME


def test_missing_ocr_value_rejected():
    assert validation_issue(sample(ocr_value=None)) == INVALID_MISSING_OCR_VALUE
    assert validation_issue(sample(ocr_value="")) == INVALID_MISSING_OCR_VALUE


def test_missing_human_value_rejected():
    assert validation_issue(sample(human_value=None)) == INVALID_MISSING_HUMAN_VALUE
    assert validation_issue(sample(human_value="")) == INVALID_MISSING_HUMAN_VALUE


def test_missing_confidence_score_rejected():
    assert validation_issue(sample(confidence_score=None)) == INVALID_CONFIDENCE_SCORE


def test_out_of_range_confidence_rejected():
    assert validation_issue(sample(confidence_score=-0.1)) == INVALID_CONFIDENCE_SCORE
    assert validation_issue(sample(confidence_score=1.5)) == INVALID_CONFIDENCE_SCORE


def test_boundary_confidence_accepted():
    assert validation_issue(sample(confidence_score=0.0)) is None
    assert validation_issue(sample(confidence_score=1.0)) is None


def test_unknown_decision_rejected():
    assert validation_issue(sample(decision="BOGUS")) == INVALID_DECISION


def test_known_decisions_accepted():
    for decision in ("APPROVE", "CORRECT", "REJECT", "CORRECTED"):
        assert validation_issue(sample(decision=decision)) is None


def test_missing_decision_is_optional():
    assert validation_issue(sample(decision=None)) is None


def test_validation_issue_precedence():
    entry = sample(
        application_id=None,
        field_name="",
        ocr_value=None,
        human_value=None,
        confidence_score=None,
        decision="BOGUS",
    )
    assert validation_issue(entry) == INVALID_MISSING_APPLICATION_ID


def test_duplicate_signature_stable_for_identical_samples():
    first = sample(id=1, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = sample(id=2, recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert duplicate_signature(first) == duplicate_signature(second)


def test_duplicate_signature_differs_on_key_fields():
    base = sample(recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert duplicate_signature(base) != duplicate_signature(
        sample(ocr_value="different", recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    )
    assert duplicate_signature(base) != duplicate_signature(
        sample(human_value="different", recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    )


def test_build_record_resolves_document_type():
    entry = sample(
        document_id=20,
        normalized_value="9999999999",
        confidence_source="regex",
        reviewer="alice",
        origin="FINAL_HUMAN_REVIEW",
        recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    record = build_record(entry, {20: DocumentType.ONE_LINK_LETTER})
    assert record["application_id"] == 10
    assert record["document_type"] == "ONE_LINK_LETTER"
    assert record["field_name"] == "account_number"
    assert record["original_ocr_value"] == "1234567890"
    assert record["normalized_value"] == "9999999999"
    assert record["human_corrected_value"] == "9999999999"
    assert record["confidence_score"] == 0.85
    assert record["confidence_source"] == "regex"
    assert record["correction_reason"] is None
    assert record["decision"] == "CORRECT"
    assert record["origin"] == "FINAL_HUMAN_REVIEW"
    assert record["recorded_at"] == "2026-01-01T00:00:00+00:00"
    assert set(record) == set(CSV_COLUMNS)


def test_build_record_unknown_document_type_fallback():
    record = build_record(sample(document_id=None), {})
    assert record["document_type"] == "UNKNOWN"


def test_build_record_naive_timestamp_normalized_to_utc():
    record = build_record(sample(recorded_at=datetime(2026, 1, 1)), {})
    assert record["recorded_at"] == "2026-01-01T00:00:00+00:00"


def test_reviewer_label_falls_back_to_unknown():
    assert reviewer_label(sample(reviewer=None)) == "UNKNOWN"
    assert reviewer_label(sample(reviewer="alice")) == "alice"


def test_confidence_bucket_boundaries():
    assert confidence_bucket(0.0) == "0.00-0.20"
    assert confidence_bucket(0.199999) == "0.00-0.20"
    assert confidence_bucket(0.2) == "0.20-0.40"
    assert confidence_bucket(0.8) == "0.80-1.00"
    assert confidence_bucket(1.0) == "0.80-1.00"


def test_canonical_json_is_deterministic():
    first = build_record(sample(id=1), {20: DocumentType.ONE_LINK_LETTER})
    second = build_record(
        sample(id=2, human_value="8888888888"), {20: DocumentType.ONE_LINK_LETTER}
    )
    again_first = build_record(sample(id=1), {20: DocumentType.ONE_LINK_LETTER})
    assert canonical_records_json([first, second]) == canonical_records_json(
        [again_first, second]
    )
    assert canonical_records_json([first, second]) != canonical_records_json(
        [second, first]
    )


def test_canonical_json_is_compact_and_sorted():
    record = build_record(sample(id=1), {20: DocumentType.ONE_LINK_LETTER})
    serialized = canonical_records_json([record])
    assert " " not in serialized
    assert '"field_name":"account_number"' in serialized
    assert '"recorded_at":"2026-01-01T00:00:00+00:00"' in serialized
    assert serialized.startswith('[{"')
    assert serialized.endswith("}]")
    assert serialized.index('"application_id"') < serialized.index('"decision"')
    assert serialized == canonical_records_json(
        [build_record(sample(id=1), {20: DocumentType.ONE_LINK_LETTER})]
    )


def test_compute_completeness_empty_is_zero():
    assert compute_completeness([], []) == {
        "document_type": 0.0,
        "normalized_value": 0.0,
        "confidence_source": 0.0,
        "correction_reason": 0.0,
        "decision": 0.0,
        "origin": 0.0,
        "reviewer": 0.0,
    }


def test_compute_completeness_partial():
    records = [
        build_record(sample(id=1), {20: DocumentType.ONE_LINK_LETTER}),
        build_record(sample(id=2, document_id=None, reviewer=None), {}),
        build_record(sample(id=3, document_id=None, normalized_value="x"), {}),
    ]
    reviewers = ["alice", "UNKNOWN", "bob"]
    completeness = compute_completeness(records, reviewers)
    assert completeness["document_type"] == round(1 / 3, 4)
    assert completeness["normalized_value"] == round(1 / 3, 4)
    assert completeness["reviewer"] == round(2 / 3, 4)
    assert completeness["decision"] == 1.0
