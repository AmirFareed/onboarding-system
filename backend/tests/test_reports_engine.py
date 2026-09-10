"""Pure unit tests for the validation report derivation helpers.

These tests exercise the deterministic, database-free logic of the report
module: the category-to-group mapping, the overall status precedence and the
recommendation builder. None of them touch the database.
"""

import pytest

from app.database.models.enums import ApplicationStatus
from app.reports.constants import (
    GROUP_SIGNATURE,
    GROUP_STAMP,
    RECOMMENDATION_ORDER,
    ReportOverallStatus,
)
from app.reports.validators import (
    build_recommendations,
    derive_overall_status,
    group_label,
)


# --- Category grouping -------------------------------------------------------


@pytest.mark.parametrize(
    ("category", "rule_id", "expected"),
    [
        ("document_completeness", "DOC_AMC_PRESENT", "Document Validation"),
        ("field_presence", "FLD_IBAN_PRESENT", "Document Validation"),
        ("format", "FMT_IBAN", "Format Validation"),
        ("cross_document", "CROSS_IBAN_MATCH", "Cross Document Validation"),
        ("date", "DATE_PERIOD_SEQUENCE", "Date Validation"),
        ("policy", "POL_BALANCE_RECONCILIATION", "Business Policy Validation"),
        ("quality", "QUAL_TRANSACTION_COUNT", "Quality Validation"),
    ],
)
def test_group_label_maps_rule_categories(category, rule_id, expected):
    assert group_label(category, rule_id) == expected


@pytest.mark.parametrize(
    ("rule_id", "expected"),
    [
        ("VIS_SIGNATURE_TRIPARTITE", GROUP_SIGNATURE),
        ("VIS_SIGNATURE_FORMAL_REQUEST", GROUP_SIGNATURE),
        ("VIS_STAMP_AMC", GROUP_STAMP),
        ("VIS_STAMP_BILATERAL", GROUP_STAMP),
    ],
)
def test_group_label_splits_visual_by_prefix(rule_id, expected):
    assert group_label("visual", rule_id) == expected


def test_group_label_unknown_category_falls_back_to_category():
    assert group_label("future_category", "FUTURE_RULE") == "future_category"


# --- Overall status derivation -----------------------------------------------


@pytest.mark.parametrize(
    ("application_status", "has_failure", "has_pending", "expected"),
    [
        (None, False, False, ReportOverallStatus.APPROVED),
        (None, False, True, ReportOverallStatus.MANUAL_REVIEW_REQUIRED),
        (None, True, False, ReportOverallStatus.FAILED),
        (None, True, True, ReportOverallStatus.FAILED),
        (ApplicationStatus.SUBMITTED.value, False, False, ReportOverallStatus.APPROVED),
        (ApplicationStatus.APPROVED.value, False, False, ReportOverallStatus.APPROVED),
        (ApplicationStatus.REJECTED.value, True, True, ReportOverallStatus.REJECTED),
        (ApplicationStatus.REJECTED.value, False, False, ReportOverallStatus.REJECTED),
    ],
)
def test_derive_overall_status_precedence(
    application_status,
    has_failure,
    has_pending,
    expected,
):
    assert (
        derive_overall_status(
            application_status=application_status,
            has_failure=has_failure,
            has_pending_review=has_pending,
        )
        is expected
    )


def test_warnings_never_block_approval():
    # Warnings are informational: a run with only warnings is approved.
    assert (
        derive_overall_status(
            application_status=ApplicationStatus.SUBMITTED.value,
            has_failure=False,
            has_pending_review=False,
        )
        is ReportOverallStatus.APPROVED
    )


# --- Recommendation builder --------------------------------------------------


def test_recommendations_empty_when_nothing_applicable():
    assert build_recommendations({}) == []


def test_recommendations_no_action_only_when_approved():
    result = build_recommendations({"approved": True})
    assert [item["code"] for item in result] == ["NO_ACTION_REQUIRED"]


def test_recommendations_no_action_suppressed_by_other_findings():
    result = build_recommendations({"approved": True, "date_failures": True})
    assert [item["code"] for item in result] == ["REVIEW_DATES"]


def test_recommendations_order_is_deterministic():
    findings = {
        "missing_document_types": ["TRIPARTITE_AGREEMENT"],
        "missing_signature_documents": ["ONE_LINK_LETTER"],
        "iban_inconsistent": True,
        "low_confidence": True,
    }
    result = [item["code"] for item in build_recommendations(findings)]
    assert result == [
        "MISSING_REQUIRED_DOCUMENT",
        "MISSING_SIGNATURE",
        "IBAN_INCONSISTENCY",
        "CORRECT_LOW_CONFIDENCE",
    ]
    assert result == [
        code for code in RECOMMENDATION_ORDER if code in result
    ]


def test_recommendations_duplicate_document_is_distinct_from_missing():
    # A document present more than once must not read as "missing" -- see
    # the 2026-08-25 ONE_LINK_LETTER finding in CONTEXT.md.
    result = build_recommendations(
        {
            "missing_document_types": ["TRIPARTITE_AGREEMENT"],
            "duplicate_document_types": ["ONE_LINK_LETTER"],
        }
    )
    codes = [item["code"] for item in result]
    assert codes == ["MISSING_REQUIRED_DOCUMENT", "DUPLICATE_REQUIRED_DOCUMENT"]
    missing = next(item for item in result if item["code"] == "MISSING_REQUIRED_DOCUMENT")
    duplicate = next(item for item in result if item["code"] == "DUPLICATE_REQUIRED_DOCUMENT")
    assert "ONE_LINK_LETTER" not in missing["message"]
    assert "ONE_LINK_LETTER" in duplicate["message"]
    assert "TRIPARTITE_AGREEMENT" not in duplicate["message"]


def test_recommendations_details_joined_in_order():
    result = build_recommendations(
        {
            "missing_document_types": ["TRIPARTITE_AGREEMENT", "ONE_LINK_LETTER"],
            "missing_stamp_documents": ["ACCOUNT_MAINTENANCE_CERTIFICATE"],
        }
    )
    missing = next(
        item for item in result if item["code"] == "MISSING_REQUIRED_DOCUMENT"
    )
    assert missing["message"].endswith("TRIPARTITE_AGREEMENT, ONE_LINK_LETTER.")
    stamps = next(item for item in result if item["code"] == "MISSING_STAMP")
    assert stamps["message"].endswith("ACCOUNT_MAINTENANCE_CERTIFICATE.")
