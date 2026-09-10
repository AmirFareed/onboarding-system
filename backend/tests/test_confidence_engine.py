"""Unit tests for the confidence scoring engine.

Exercises the pure scoring helpers (source confidence, template coverage,
weighted blend with renormalization, reason generation, status decision) and
the review-payload validation rules in isolation, without a database.
"""

import pytest

from app.confidence.constants import (
    REASON_LOW_OCR,
    REASON_MISSING_CONTEXT,
    REASON_REGEX_MISMATCH,
    REASON_TEMPLATE_MISMATCH,
    REASON_VALID,
    EvaluationStatus,
    is_critical,
)
from app.confidence.exceptions import InvalidReviewPayload
from app.confidence.schemas import (
    ReviewDecisionInput,
    ReviewDecisionType,
    ReviewRequest,
)
from app.confidence.services import (
    build_confidence_reason,
    compute_field_confidence,
    decide_processing_status,
    find_validation_status,
    regex_source_confidence,
    template_coverage,
)
from app.confidence.validators import validate_review_request

DEFAULT_WEIGHTS = {"regex": 0.50, "template": 0.30, "ocr": 0.20, "ai": 0.00}


# --- Regex source confidence -------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("valid", 1.0),
        ("invalid", 0.25),
        ("missing", 0.0),
        (None, 1.0),
    ],
)
def test_regex_source_confidence_maps_validation_status(status, expected):
    assert regex_source_confidence(status) == expected


def test_find_validation_status_returns_matching_entry():
    results = [
        {"field": "iban", "status": "valid"},
        {"field": "bank_name", "status": "valid"},
    ]
    assert find_validation_status(results, "iban") == "valid"
    assert find_validation_status(results, "missing_field") is None
    assert find_validation_status([], "iban") is None


# --- Template coverage -------------------------------------------------------


def test_template_coverage_full_when_everything_expected_is_present():
    assert template_coverage({"a", "b", "c"}, {"a", "b", "c", "d"}) == 1.0


def test_template_coverage_partial():
    assert template_coverage({"a", "b", "c", "d"}, {"a", "b"}) == 0.5


def test_template_coverage_zero_when_nothing_present():
    assert template_coverage({"a", "b"}, set()) == 0.0


def test_template_coverage_full_when_nothing_expected():
    assert template_coverage(set(), set()) == 1.0
    assert template_coverage(set(), {"a"}) == 1.0


# --- Weighted blend ----------------------------------------------------------


def test_blend_uses_all_available_sources():
    sources = {"regex": 1.0, "template": 1.0, "ocr": 0.9, "ai": None}
    score, primary = compute_field_confidence(DEFAULT_WEIGHTS, sources)
    assert score == pytest.approx((0.5 * 1.0 + 0.3 * 1.0 + 0.2 * 0.9) / 1.0)
    assert primary == "regex"


def test_blend_renormalizes_when_ocr_missing():
    sources = {"regex": 1.0, "template": 1.0, "ocr": None, "ai": None}
    score, primary = compute_field_confidence(DEFAULT_WEIGHTS, sources)
    assert score == pytest.approx(1.0)
    assert primary == "regex"


def test_blend_ignores_ai_when_weight_is_zero():
    sources = {"regex": 1.0, "template": 1.0, "ocr": None, "ai": 0.5}
    score, primary = compute_field_confidence(DEFAULT_WEIGHTS, sources)
    assert score == pytest.approx(1.0)
    assert primary == "regex"


def test_blend_uses_ai_when_weight_configured():
    weights = {"regex": 0.4, "template": 0.3, "ocr": 0.0, "ai": 0.3}
    sources = {"regex": 0.5, "template": 0.5, "ocr": None, "ai": 1.0}
    score, primary = compute_field_confidence(weights, sources)
    assert score == pytest.approx((0.4 * 0.5 + 0.3 * 0.5 + 0.3 * 1.0) / 1.0)
    assert primary == "ai"


def test_blend_single_source_weight():
    weights = {"regex": 0.0, "template": 0.0, "ocr": 1.0, "ai": 0.0}
    sources = {"regex": 1.0, "template": 1.0, "ocr": 0.7, "ai": None}
    score, primary = compute_field_confidence(weights, sources)
    assert score == pytest.approx(0.7)
    assert primary == "ocr"


def test_blend_clamps_out_of_range_score():
    sources = {"regex": 1.0, "template": 1.0, "ocr": 5.0, "ai": None}
    score, _ = compute_field_confidence(DEFAULT_WEIGHTS, sources)
    assert score == pytest.approx(1.0)


def test_blend_returns_zero_when_no_source_available():
    weights = {"regex": 0.0, "template": 0.0, "ocr": 0.0, "ai": 0.0}
    sources = {"regex": 1.0, "template": 1.0, "ocr": None, "ai": None}
    score, primary = compute_field_confidence(weights, sources)
    assert score == 0.0
    assert primary is None


# --- Confidence reasons ------------------------------------------------------


def test_reason_valid_when_everything_is_fine():
    assert build_confidence_reason("valid", 0.95, 1.0) == REASON_VALID


def test_reason_regex_mismatch():
    assert REASON_REGEX_MISMATCH in build_confidence_reason("invalid", 0.95, 1.0)


def test_reason_missing_context():
    assert REASON_MISSING_CONTEXT in build_confidence_reason("missing", 0.95, 1.0)


def test_reason_low_ocr():
    assert REASON_LOW_OCR in build_confidence_reason("valid", 0.2, 1.0)


def test_reason_template_mismatch():
    assert REASON_TEMPLATE_MISMATCH in build_confidence_reason("valid", 0.95, 0.4)


def test_reason_combines_fragments():
    reason = build_confidence_reason("invalid", 0.1, 0.3)
    assert REASON_REGEX_MISMATCH in reason
    assert REASON_LOW_OCR in reason
    assert REASON_TEMPLATE_MISMATCH in reason


# --- Status decision ---------------------------------------------------------


def _entry(name, score, resolved=False):
    return {"field_name": name, "score": score, "resolved": resolved}


def test_decision_ready_when_all_fields_above_threshold():
    entries = [_entry("iban", 0.9), _entry("bank_name", 1.0)]
    status, flagged, failures = decide_processing_status(entries, 0.85)
    assert status is EvaluationStatus.READY_FOR_NORMALIZATION
    assert flagged == set()
    assert failures == []


def test_decision_critical_field_below_threshold_requires_review():
    entries = [_entry("iban", 0.5), _entry("bank_name", 1.0)]
    status, flagged, failures = decide_processing_status(entries, 0.85)
    assert status is EvaluationStatus.REQUIRES_HUMAN_REVIEW
    assert flagged == {"iban"}
    assert failures == ["iban"]


def test_decision_only_non_critical_low_is_ready():
    entries = [_entry("iban", 1.0), _entry("branch", 0.2)]
    status, flagged, failures = decide_processing_status(entries, 0.85)
    assert status is EvaluationStatus.READY_FOR_NORMALIZATION
    assert flagged == set()
    assert failures == []


def test_decision_boundary_exactly_at_threshold_passes():
    assert is_critical("iban")
    entries = [_entry("iban", 0.85)]
    status, _, _ = decide_processing_status(entries, 0.85)
    assert status is EvaluationStatus.READY_FOR_NORMALIZATION


def test_decision_returns_all_low_fields_for_review():
    entries = [_entry("iban", 0.5), _entry("branch", 0.4), _entry("bank_name", 1.0)]
    status, flagged, failures = decide_processing_status(entries, 0.85)
    assert status is EvaluationStatus.REQUIRES_HUMAN_REVIEW
    assert flagged == {"iban", "branch"}
    assert failures == ["iban"]


def test_decision_ignores_human_resolved_low_fields():
    entries = [_entry("iban", 0.5, resolved=True), _entry("bank_name", 1.0)]
    status, flagged, failures = decide_processing_status(entries, 0.85)
    assert status is EvaluationStatus.READY_FOR_NORMALIZATION
    assert flagged == set()
    assert failures == []


def test_critical_field_classification():
    assert is_critical("iban")
    assert is_critical("account_number")
    assert is_critical("account_holder")
    assert is_critical("bank_name")
    assert is_critical("document_number")
    assert is_critical("date_of_birth")
    assert not is_critical("branch")
    assert not is_critical("vendor_name")


# --- Review payload validation -----------------------------------------------


def _review_request(*decisions):
    return ReviewRequest(
        decisions=[ReviewDecisionInput(**decision) for decision in decisions],
    )


def test_valid_review_payload_passes():
    request = _review_request(
        {"field_name": "iban", "decision": ReviewDecisionType.VERIFIED},
        {"field_name": "branch", "decision": ReviewDecisionType.CORRECTED, "corrected_value": "Main"},
    )
    validate_review_request(request, {"iban", "branch"})


def test_missing_decision_for_flagged_field_rejected():
    request = _review_request(
        {"field_name": "iban", "decision": ReviewDecisionType.VERIFIED}
    )
    with pytest.raises(InvalidReviewPayload):
        validate_review_request(request, {"iban", "branch"})


def test_decision_for_unflagged_field_rejected():
    request = _review_request(
        {"field_name": "iban", "decision": ReviewDecisionType.VERIFIED},
        {"field_name": "branch", "decision": ReviewDecisionType.VERIFIED},
    )
    with pytest.raises(InvalidReviewPayload):
        validate_review_request(request, {"iban"})


def test_duplicate_decision_rejected():
    request = _review_request(
        {"field_name": "iban", "decision": ReviewDecisionType.VERIFIED},
        {"field_name": "iban", "decision": ReviewDecisionType.CORRECTED, "corrected_value": "x"},
    )
    with pytest.raises(InvalidReviewPayload):
        validate_review_request(request, {"iban"})


def test_corrected_without_value_rejected():
    request = _review_request(
        {
            "field_name": "iban",
            "decision": ReviewDecisionType.CORRECTED,
            "corrected_value": None,
        }
    )
    with pytest.raises(InvalidReviewPayload):
        validate_review_request(request, {"iban"})


def test_review_with_no_flagged_fields_rejected():
    request = _review_request(
        {"field_name": "iban", "decision": ReviewDecisionType.VERIFIED}
    )
    with pytest.raises(InvalidReviewPayload):
        validate_review_request(request, set())
