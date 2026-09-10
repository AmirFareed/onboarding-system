"""Tests for the final human verification API.

End-to-end tests build validated applications through the real API and then
exercise the final review screen, the three decisions (approve, correct, reject)
and the review history. The tests assert the checklist enforcement, the
mandatory rejection reason, the corrections persistence, the double-review
prevention, the audit trail and the application status transitions.
"""

from app.database.connection import SessionLocal
from app.database.models.human_correction import HumanCorrection
from app.database.models.human_review import HumanReview
from app.database.models.manual_checklist import ManualChecklist
from app.human_verification.constants import CHECKLIST_ITEMS
from tests.test_confidence_api import audit_actions, feedback_count
from tests.test_reports_api import build_full_application, build_single_statement_application
from tests.test_technical_validation_api import create_application

API = "/api/v1"

SCREEN_URL = "/human-review"
HISTORY_URL = "/human-review/history"

REVIEW_VERSION = "1.0.0"


def checked_items(checked_names: set[str] | None = None) -> list[dict]:
    """Build a fully checked checklist, optionally leaving items unchecked."""
    checked_names = checked_names if checked_names is not None else set(CHECKLIST_ITEMS)
    return [
        {"item_name": name, "is_checked": name in checked_names}
        for name in CHECKLIST_ITEMS
    ]


def submit(client, application_id: int, payload: dict):
    """POST a final review decision and return the response."""
    return client.post(
        f"{API}/applications/{application_id}{SCREEN_URL}",
        json=payload,
    )


def stored_reviews(application_id: int) -> list[HumanReview]:
    """Return the stored human reviews for an application."""
    db = SessionLocal()
    try:
        return (
            db.query(HumanReview)
            .filter_by(application_id=application_id)
            .order_by(HumanReview.id)
            .all()
        )
    finally:
        db.close()


def stored_checklist(application_id: int) -> list[ManualChecklist]:
    """Return the stored checklist items for an application."""
    db = SessionLocal()
    try:
        return (
            db.query(ManualChecklist)
            .filter_by(application_id=application_id)
            .order_by(ManualChecklist.item_name)
            .all()
        )
    finally:
        db.close()


def _status(application_id: int) -> str:
    """Return the current status of an application."""
    from app.database.repositories.application_repository import ApplicationRepository

    db = SessionLocal()
    try:
        application = ApplicationRepository(db).get_by_id(application_id)
        return application.status.value if application is not None else None
    finally:
        db.close()


# --- Review screen -----------------------------------------------------------


def test_screen_contains_full_review_data(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)

    response = authenticated_client.get(f"{API}/applications/{application_id}{SCREEN_URL}")

    assert response.status_code == 200
    screen = response.json()
    assert screen["application_id"] == application_id
    assert screen["application"]["status"] == "SUBMITTED"
    report = screen["report"]
    assert report["report_version"] == REVIEW_VERSION
    assert report["overall_status"] == "APPROVED"
    assert len(report["document_summary"]) == 8
    assert len(screen["documents"]) == 8
    assert len(screen["visual_detections"]) == 11
    assert len(screen["fields"]) > 0
    assert all(field["normalized_value"] is not None for field in screen["fields"])
    assert [item["item_name"] for item in screen["checklist"]] == list(CHECKLIST_ITEMS)
    assert all(item["is_checked"] is False for item in screen["checklist"])
    assert screen["previous_review"] is None


def test_screen_without_validation_results_is_not_yet_reviewed(authenticated_client, storage_root):
    """The review screen embeds the same aggregated report as the Validation
    Report module (app.reports) -- an application with zero stored rule rows
    must open the screen as "not yet reviewed", not a 422 that blocks the
    reviewer from even seeing which documents are missing."""
    application_id = create_application(authenticated_client)

    response = authenticated_client.get(f"{API}/applications/{application_id}{SCREEN_URL}")

    assert response.status_code == 200, response.text
    assert response.json()["report"]["overall_status"] == "MANUAL_REVIEW_REQUIRED"


# --- Approve flow ------------------------------------------------------------


def test_approve_flow(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)

    response = submit(
        authenticated_client,
        application_id,
        {
            "decision": "APPROVE",
            "comments": "All documents verified",
            "checklist": checked_items(),
        },
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["decision"] == "APPROVE"
    assert summary["reviewer_name"] == "Test Operator"
    assert summary["application_status"] == "APPROVED"
    assert summary["checklist_checked"] == len(CHECKLIST_ITEMS)
    assert summary["checklist_total"] == len(CHECKLIST_ITEMS)
    assert summary["corrections_count"] == 0
    assert summary["rejection_reason"] is None

    assert _status(application_id) == "APPROVED"
    reviews = stored_reviews(application_id)
    assert len(reviews) == 1
    assert reviews[0].decision.value == "APPROVE"
    assert reviews[0].comments == "All documents verified"
    assert reviews[0].rejection_reason is None

    checklist = stored_checklist(application_id)
    assert len(checklist) == len(CHECKLIST_ITEMS)
    assert all(item.is_checked for item in checklist)
    assert all(item.reviewer == "Test Operator" for item in checklist)

    actions = audit_actions(application_id)
    assert "human_review.submitted" in actions
    assert "human_review.application_approved" in actions
    assert "human_review.checklist_completed" in actions


def test_approve_requires_full_checklist(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)

    response = submit(
        authenticated_client,
        application_id,
        {
            "decision": "APPROVE",
            "checklist": checked_items(checked_names=set(CHECKLIST_ITEMS) - {CHECKLIST_ITEMS[0]}),
        },
    )

    assert response.status_code == 422
    assert "checklist" in response.json()["detail"].lower()
    assert _status(application_id) != "APPROVED"
    assert stored_reviews(application_id) == []


# --- Correction flow ---------------------------------------------------------


def test_correct_flow(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    assert feedback_count(application_id) == 0

    response = submit(
        authenticated_client,
        application_id,
        {
            "decision": "CORRECT",
            "comments": "Account number corrected after manual check",
            "corrections": [
                {
                    "field_name": "account_number",
                    "corrected_value": "9999999999",
                    "reason": "digits misread",
                }
            ],
        },
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["decision"] == "CORRECT"
    assert summary["application_status"] == "CORRECTED"
    assert summary["corrections_count"] == 1

    assert _status(application_id) == "CORRECTED"
    reviews = stored_reviews(application_id)
    assert len(reviews) == 1
    assert reviews[0].decision.value == "CORRECT"

    db = SessionLocal()
    try:
        correction = (
            db.query(HumanCorrection).filter_by(review_id=reviews[0].id).first()
        )
        assert correction.field_name == "account_number"
        assert correction.corrected_value == "9999999999"
        assert correction.reason == "digits misread"
        assert correction.original_value == "1234567890"
    finally:
        db.close()

    from app.database.repositories.extracted_field_repository import ExtractedFieldRepository

    db = SessionLocal()
    try:
        fields = ExtractedFieldRepository(db).get_by_application(application_id)
        account_number = next(f for f in fields if f.field_name == "account_number")
    finally:
        db.close()
    assert account_number.human_corrected_value == "9999999999"
    assert account_number.human_verified is True
    assert account_number.reviewer == "Test Operator"
    assert account_number.reviewed_at is not None

    assert feedback_count(application_id) == 1
    actions = audit_actions(application_id)
    assert "human_review.submitted" in actions
    assert "human_review.application_corrected" in actions


def test_correct_disambiguates_same_named_field_by_document(authenticated_client, storage_root):
    """Two documents extracting the same field name must be corrected independently."""
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)

    screen = authenticated_client.get(f"{API}/applications/{application_id}{SCREEN_URL}").json()
    account_number_fields = [f for f in screen["fields"] if f["field_name"] == "account_number"]
    assert len(account_number_fields) >= 2, "fixture must produce the field on multiple documents"
    first, second = account_number_fields[0], account_number_fields[1]
    assert first["document_id"] != second["document_id"]

    response = submit(
        authenticated_client,
        application_id,
        {
            "decision": "CORRECT",
            "corrections": [
                {
                    "field_name": "account_number",
                    "document_id": first["document_id"],
                    "corrected_value": "1111111111",
                },
                {
                    "field_name": "account_number",
                    "document_id": second["document_id"],
                    "corrected_value": "2222222222",
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["corrections_count"] == 2

    from app.database.repositories.extracted_field_repository import ExtractedFieldRepository

    db = SessionLocal()
    try:
        fields = ExtractedFieldRepository(db).get_by_application(application_id)
        by_document = {
            f.ocr_result.document_id: f for f in fields if f.field_name == "account_number"
        }
    finally:
        db.close()

    assert by_document[first["document_id"]].human_corrected_value == "1111111111"
    assert by_document[second["document_id"]].human_corrected_value == "2222222222"


def test_correct_requires_corrections(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = submit(
        authenticated_client,
        application_id,
        {"decision": "CORRECT"},
    )

    assert response.status_code == 422
    assert "correction" in response.json()["detail"].lower()
    assert _status(application_id) != "CORRECTED"
    assert stored_reviews(application_id) == []


# --- Reject flow -------------------------------------------------------------


def test_reject_flow(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = submit(
        authenticated_client,
        application_id,
        {
            "decision": "REJECT",
            "comments": "Documents appear tampered",
            "rejection_reason": "Detected signs of document tampering",
        },
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["decision"] == "REJECT"
    assert summary["application_status"] == "REJECTED"
    assert summary["rejection_reason"] == "Detected signs of document tampering"

    assert _status(application_id) == "REJECTED"
    reviews = stored_reviews(application_id)
    assert len(reviews) == 1
    assert reviews[0].decision.value == "REJECT"
    assert reviews[0].rejection_reason == "Detected signs of document tampering"
    assert reviews[0].comments == "Documents appear tampered"

    actions = audit_actions(application_id)
    assert "human_review.submitted" in actions
    assert "human_review.application_rejected" in actions
    assert "human_review.application_approved" not in actions


def test_reject_requires_reason(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = submit(
        authenticated_client,
        application_id,
        {"decision": "REJECT", "comments": "no"},
    )

    assert response.status_code == 422
    assert "rejection reason" in response.json()["detail"].lower()
    assert _status(application_id) != "REJECTED"
    assert stored_reviews(application_id) == []


def test_reject_with_corrections_is_inconsistent(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = submit(
        authenticated_client,
        application_id,
        {
            "decision": "REJECT",
            "rejection_reason": "tampered",
            "corrections": [
                {"field_name": "account_number", "corrected_value": "9999999999"}
            ],
        },
    )

    assert response.status_code == 400
    assert stored_reviews(application_id) == []


# --- Reviewer identity is session-derived -------------------------------------


def test_reviewer_identity_is_session_derived_not_spoofable(authenticated_client, storage_root):
    """A reviewer_name in the request body must never override the session's identity."""
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = submit(
        authenticated_client,
        application_id,
        {
            "reviewer_name": "someone-else",
            "decision": "REJECT",
            "rejection_reason": "tampered",
        },
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["reviewer_name"] == "Test Operator"
    assert summary["reviewer_name"] != "someone-else"

    reviews = stored_reviews(application_id)
    assert reviews[0].reviewer_name == "Test Operator"


# --- Double review prevention ------------------------------------------------


def test_double_review_prevented(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    submit(
        authenticated_client,
        application_id,
        {
            "decision": "REJECT",
            "rejection_reason": "tampered",
        },
    )

    response = submit(
        authenticated_client,
        application_id,
        {
            "decision": "APPROVE",
            "checklist": checked_items(),
        },
    )

    assert response.status_code == 409
    assert "already" in response.json()["detail"]
    assert _status(application_id) == "REJECTED"
    assert len(stored_reviews(application_id)) == 1


# --- History -----------------------------------------------------------------


def test_history_returns_reviews_with_corrections(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    submit(
        authenticated_client,
        application_id,
        {
            "decision": "CORRECT",
            "corrections": [
                {"field_name": "account_number", "corrected_value": "9999999999"}
            ],
        },
    )

    response = authenticated_client.get(f"{API}/applications/{application_id}{HISTORY_URL}")

    assert response.status_code == 200
    history = response.json()
    assert history["application_id"] == application_id
    assert len(history["reviews"]) == 1
    review = history["reviews"][0]
    assert review["decision"] == "CORRECT"
    assert review["reviewer_name"] == "Test Operator"
    assert review["checklist_total"] == len(CHECKLIST_ITEMS)
    assert len(review["corrections"]) == 1
    assert review["corrections"][0]["field_name"] == "account_number"
    assert review["corrections"][0]["corrected_value"] == "9999999999"


def test_history_is_empty_before_review(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = authenticated_client.get(f"{API}/applications/{application_id}{HISTORY_URL}")

    assert response.status_code == 200
    assert response.json()["reviews"] == []


# --- Error paths -------------------------------------------------------------


def test_endpoints_application_not_found(authenticated_client):
    for url in (SCREEN_URL, HISTORY_URL):
        response = authenticated_client.get(f"{API}/applications/999999{url}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Application not found"

    response = submit(
        authenticated_client,
        999999,
        {"decision": "REJECT", "rejection_reason": "x"},
    )
    assert response.status_code == 404


def test_payload_validation_rejects_unknown_decision(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = submit(
        authenticated_client,
        application_id,
        {"decision": "NONSENSE"},
    )

    assert response.status_code == 422


def test_approve_with_unknown_checklist_item_rejected(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)
    items = checked_items() + [{"item_name": "Unknown item", "is_checked": True}]

    response = submit(
        authenticated_client,
        application_id,
        {"decision": "APPROVE", "checklist": items},
    )

    assert response.status_code == 400
    assert "Unknown checklist item" in response.json()["detail"]


def test_screen_and_history_are_idempotent(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    first = authenticated_client.get(f"{API}/applications/{application_id}{SCREEN_URL}").json()
    second = authenticated_client.get(f"{API}/applications/{application_id}{SCREEN_URL}").json()
    first["report"].pop("generated_at")
    second["report"].pop("generated_at")
    assert first == second

    first_history = authenticated_client.get(f"{API}/applications/{application_id}{HISTORY_URL}").json()
    second_history = authenticated_client.get(f"{API}/applications/{application_id}{HISTORY_URL}").json()
    assert first_history == second_history
