"""Tests for the confidence API and end-to-end confidence flow.

End-to-end tests exercise the full chain through the real API: upload, Phase 5
technical validation, Phase 6 document processing, Phase 7 analysis and finally
Phase 8 confidence evaluation and review. Digital PDFs carry their analysis text
directly; scanned images use the deterministic fake OCR engine so no PaddleOCR
model is required.
"""

import logging

import pytest
from sqlalchemy import inspect

from app.core.config import get_settings
from app.database.connection import SessionLocal, engine
from app.database.models.audit_log import AuditLog
from app.database.models.enums import DocumentType
from app.database.models.extracted_field import ExtractedField
from app.database.models.feedback_dataset import FeedbackEntry
from app.database.repositories.extracted_field_repository import ExtractedFieldRepository
from tests.test_document_analysis_api import (
    BANK_STATEMENT_TEXT,
    add_digital_pdf,
    analyze_documents,
    run_processing,
)
from tests.test_document_processing_api import patch_ocr_engine, process_documents
from tests.test_technical_validation_api import (
    add_document,
    create_application,
    encode_png,
    make_document_image,
    run_validation,
)

API = "/api/v1"

EVALUATE_URL = "/confidence/evaluate"
REVIEW_URL = "/confidence/review"

#: Synthetic (fabricated), unrelated to any real document -- matches none of
#: _DETECTION_KEYWORDS' 4 categories, so it classifies as UNKNOWN and
#: extracts zero fields. Deliberately dense/multi-line (not short, like
#: PLAIN_TEXT elsewhere), to avoid tripping the unrelated pre-existing
#: blank-page technical-validation regression on a too-sparse rendered page.
UNRELATED_DENSE_TEXT = """MEETING MINUTES
Date: 2026-01-15
Attendees: Board of Directors
Topic: Quarterly Review
Location: Head Office, Conference Room A
Chairperson: J. Smith
Secretary: A. Jones
Agenda Item 1: Welcome and apologies for absence.
Agenda Item 2: Approval of previous minutes.
Agenda Item 3: Overview presented by the treasurer.
Agenda Item 4: Any other business.
Next Meeting: 2026-04-15
"""


def evaluate(client, application_id: int) -> dict:
    """Call the evaluate endpoint and return the JSON response."""
    response = client.post(f"{API}/applications/{application_id}{EVALUATE_URL}")
    assert response.status_code == 200, response.text
    return response.json()


def review(client, application_id: int, decisions: list[dict]) -> dict:
    """Call the review endpoint and return the JSON response."""
    response = client.post(
        f"{API}/applications/{application_id}{REVIEW_URL}",
        json={"decisions": decisions},
    )
    assert response.status_code == 200, response.text
    return response.json()


def add_digital_statement(client, storage_root) -> int:
    """Upload + validate + process + analyze a digital statement; return id."""
    application_id = create_application(client)
    add_digital_pdf(storage_root, application_id, BANK_STATEMENT_TEXT)
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    return application_id


def add_scanned_statement(
    client,
    storage_root,
    monkeypatch,
    *,
    confidence: float = 0.2,
) -> int:
    """Upload + validate + OCR a scanned bank statement; return its id.

    Uses DocumentType.SCHEDULE_OF_CHARGES as a storage type with no real
    extractor of its own, so BANK_STATEMENT_TEXT below reaches the generic
    OCR-keyword classifier instead of being routed to a checklist-type
    extractor (app.document_analysis.services._CHECKLIST_TYPE_MAP). Was
    DocumentType.ONE_LINK_LETTER until that type got a real extractor (Phase
    1, fifth checklist type) -- see the same swap and rationale in
    test_document_analysis_api.py's test_analyze_payslip_from_scanned_image.
    """
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.SCHEDULE_OF_CHARGES,
        "statement.png",
        encode_png(make_document_image()),
        "image/png",
    )
    run_validation(client, application_id)
    patch_ocr_engine(
        monkeypatch,
        texts=[BANK_STATEMENT_TEXT],
        confidence=confidence,
    )
    process_documents(client, application_id)
    analyze_documents(client, application_id)
    return application_id


def stored_fields(application_id: int) -> dict[str, ExtractedField]:
    """Return the persisted extracted field rows for an application."""
    db = SessionLocal()
    try:
        return {
            field.field_name: field
            for field in ExtractedFieldRepository(db).get_by_application(application_id)
        }
    finally:
        db.close()


def audit_actions(application_id: int) -> list[str]:
    """Return the audit action identifiers recorded for an application."""
    db = SessionLocal()
    try:
        return [
            entry.action
            for entry in db.query(AuditLog)
            .filter_by(application_id=application_id)
            .order_by(AuditLog.id)
            .all()
        ]
    finally:
        db.close()


def feedback_count(application_id: int) -> int:
    """Return the number of feedback samples recorded for an application."""
    db = SessionLocal()
    try:
        return db.query(FeedbackEntry).filter_by(application_id=application_id).count()
    finally:
        db.close()


def _decisions(decisions: list[tuple[str, str, str | None]]) -> list[dict]:
    """Build decision payloads as (field_name, decision, corrected_value)."""
    return [
        {
            "field_name": name,
            "decision": decision,
            **({"corrected_value": value} if value is not None else {}),
        }
        for name, decision, value in decisions
    ]


def _verified_decisions(flagged: list[dict], exclude: set[str]) -> list[tuple[str, str, str | None]]:
    """Build VERIFIED decisions for every flagged field except ``exclude``."""
    return [
        (field["field_name"], "VERIFIED", None)
        for field in flagged
        if field["field_name"] not in exclude
    ]


# --- High confidence ---------------------------------------------------------


def test_evaluate_high_confidence_is_ready(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)

    result = evaluate(authenticated_client, application_id)

    assert result["application_id"] == application_id
    assert result["processing_status"] == "READY_FOR_NORMALIZATION"
    assert result["overall_confidence"] == 1.0
    assert result["threshold"] == 0.85
    assert result["fields_requiring_review"] == []
    assert result["critical_failures"] == []

    fields = stored_fields(application_id)
    assert len(fields) == 11
    assert fields["account_number"].confidence_score == 1.0
    assert fields["account_number"].verification_status == "AUTO_VERIFIED"
    assert fields["account_number"].confidence_source == "regex"
    assert fields["account_number"].confidence_reason == "Validated by extraction"
    assert "confidence.evaluated" in audit_actions(application_id)


def test_digital_pdf_fields_renormalize_without_ocr(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)
    result = evaluate(authenticated_client, application_id)
    assert result["processing_status"] == "READY_FOR_NORMALIZATION"
    assert all(
        field.confidence_score == 1.0
        for field in stored_fields(application_id).values()
    )


# --- Low confidence ----------------------------------------------------------


def test_evaluate_low_confidence_requires_review(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)

    result = evaluate(authenticated_client, application_id)

    assert result["processing_status"] == "REQUIRES_HUMAN_REVIEW"
    assert result["overall_confidence"] == pytest.approx(0.84)
    assert result["fields_requiring_review"]
    assert result["critical_failures"]

    reviewable = {field["field_name"] for field in result["fields_requiring_review"]}
    assert "account_number" in reviewable
    assert "iban" in reviewable
    for field in result["fields_requiring_review"]:
        assert field["verification_status"] == "PENDING_REVIEW"
        assert field["confidence_score"] < result["threshold"]
        assert field["confidence_reason"] == "Low OCR confidence"
    assert "account_number" in result["critical_failures"]

    fields = stored_fields(application_id)
    assert fields["account_number"].verification_status == "PENDING_REVIEW"
    assert fields["account_number"].confidence_source == "regex"


def test_evaluate_returns_only_low_fields_for_review(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)

    result = evaluate(authenticated_client, application_id)

    reviewable = {
        field["field_name"] for field in result["fields_requiring_review"]
    }
    assert reviewable == set(stored_fields(application_id))
    assert all(
        field["confidence_score"] < result["threshold"]
        for field in result["fields_requiring_review"]
    )


# --- Human review workflows --------------------------------------------------


def test_review_verify_all_fields_ready(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]

    decisions = [
        (field["field_name"], "VERIFIED", None) for field in flagged
    ]
    result = review(authenticated_client, application_id, _decisions(decisions))

    assert result["processing_status"] == "READY_FOR_NORMALIZATION"

    fields = stored_fields(application_id)
    for field in fields.values():
        assert field.human_verified is True
        assert field.confidence_score == 1.0
        assert field.reviewer == "Test Operator"
        assert field.reviewed_at is not None
        assert field.verification_status in {"VERIFIED", "AUTO_VERIFIED"}
    actions = audit_actions(application_id)
    assert actions.count("confidence.field_verified") == len(flagged)
    assert "confidence.reviewed" in actions


def test_review_correct_field_updates_value_and_feedback(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]

    decisions = _verified_decisions(flagged, {"account_number"})
    decisions.append(("account_number", "CORRECTED", "9999999999"))
    result = review(authenticated_client, application_id, _decisions(decisions))
    assert result["processing_status"] == "READY_FOR_NORMALIZATION"

    fields = stored_fields(application_id)
    corrected = fields["account_number"]
    assert corrected.verification_status == "CORRECTED"
    assert corrected.human_verified is True
    assert corrected.human_corrected_value == "9999999999"
    assert corrected.extracted_value == "9999999999"
    assert corrected.confidence_score == 1.0
    assert corrected.reviewer == "Test Operator"
    assert corrected.reviewed_at is not None

    assert feedback_count(application_id) == 1
    db = SessionLocal()
    try:
        entry = db.query(FeedbackEntry).filter_by(application_id=application_id).first()
        assert entry.field_name == "account_number"
        assert entry.ocr_value == "1234567890"
        assert entry.human_value == "9999999999"
        assert entry.confidence_score == pytest.approx(0.84)
    finally:
        db.close()
    actions = audit_actions(application_id)
    assert "confidence.field_corrected" in actions


def test_review_cannot_verify_halts_processing(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]

    decisions = _verified_decisions(flagged, {"iban"})
    decisions.append(("iban", "CANNOT_VERIFY", None))
    result = review(authenticated_client, application_id, _decisions(decisions))

    assert result["processing_status"] == "PROCESSING_HALTED"

    fields = stored_fields(application_id)
    assert fields["iban"].verification_status == "CANNOT_VERIFY"
    actions = audit_actions(application_id)
    assert "confidence.field_cannot_verify" in actions
    assert "confidence.processing_halted" in actions


# --- Re-evaluation -----------------------------------------------------------


def test_reevaluate_upserts_single_row_per_field(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)

    first = evaluate(authenticated_client, application_id)
    second = evaluate(authenticated_client, application_id)

    assert first["processing_status"] == "REQUIRES_HUMAN_REVIEW"
    assert second["processing_status"] == "REQUIRES_HUMAN_REVIEW"
    fields = stored_fields(application_id)
    assert len(fields) == 11


def test_reevaluate_preserves_human_review(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]
    decisions = _verified_decisions(flagged, {"account_number"})
    decisions.append(("account_number", "CORRECTED", "9999999999"))
    review(authenticated_client, application_id, _decisions(decisions))

    re_evaluated = evaluate(authenticated_client, application_id)

    assert re_evaluated["processing_status"] == "READY_FOR_NORMALIZATION"
    assert re_evaluated["fields_requiring_review"] == []
    assert len(stored_fields(application_id)) == 11
    corrected = stored_fields(application_id)["account_number"]
    assert corrected.human_verified is True
    assert corrected.verification_status == "CORRECTED"
    assert corrected.human_corrected_value == "9999999999"
    assert corrected.confidence_score == 1.0
    assert corrected.extracted_value == "9999999999"


# --- Threshold boundary ------------------------------------------------------


def test_threshold_boundary_uses_settings(authenticated_client, storage_root, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "confidence_threshold", 0.84)
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)

    result = evaluate(authenticated_client, application_id)

    assert result["threshold"] == 0.84
    assert result["processing_status"] == "READY_FOR_NORMALIZATION"


# --- Error paths -------------------------------------------------------------


def test_evaluate_application_not_found(authenticated_client):
    response = authenticated_client.post(f"{API}/applications/999999{EVALUATE_URL}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"


def test_evaluate_no_analysis_results(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    response = authenticated_client.post(f"{API}/applications/{application_id}{EVALUATE_URL}")
    assert response.status_code == 422
    assert "analysis" in response.json()["detail"].lower()


def test_evaluate_with_zero_extracted_fields_does_not_500(
    authenticated_client, storage_root, caplog
):
    """An application whose only analyzed document extracted zero fields must
    still return a valid (if degenerate) response, not crash.

    Regression test for a real bug found 2026-08-17 (see CONTEXT.md):
    ConfidenceService.evaluate()'s completion log line formatted `overall`
    with %.3f, but `overall` is None whenever no fields were collected --
    unhandled, so this raised TypeError and 500'd instead of returning
    overall_confidence=None (already the schema's own documented meaning for
    "nothing was scored", matching the same None-not-zero convention used
    independently in reports/services.py's own overall-confidence field).

    caplog.set_level(logging.INFO) is required, not decorative: pytest's log
    capture handler defaults to WARNING, and Python's %-style logging only
    performs the actual substitution when a handler at-or-below the record's
    level formats it -- so without this, the buggy %.3f line's TypeError
    never fires during a test run at all (confirmed directly: this exact
    test still passed with the bug still in place until this line was
    added). This matches CONTEXT.md's own B.8 audit finding that the bug is
    "dormant in tests, live in code" -- explains why, not just states it.

    UNRELATED_DENSE_TEXT is deliberately long and label-dense (not short,
    like PLAIN_TEXT elsewhere in this file) purely to avoid tripping the
    unrelated pre-existing blank-page technical-validation regression
    (fcc9fda, tracked in CONTEXT.md) on a too-sparse rendered page -- and
    deliberately avoids every _DETECTION_KEYWORDS phrase (bank statement,
    payslip, ID document, tax document) so it classifies as UNKNOWN and
    genuinely extracts zero fields, the real condition this bug needs.
    """
    caplog.set_level(logging.INFO)
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        UNRELATED_DENSE_TEXT,
        filename="minutes.pdf",
    )
    run_processing(authenticated_client, application_id)
    analysis = analyze_documents(authenticated_client, application_id)
    assert analysis["total_analyzed"] == 1
    assert analysis["items"][0]["document_type"] == "UNKNOWN"

    result = evaluate(authenticated_client, application_id)

    assert result["overall_confidence"] is None
    assert result["fields_requiring_review"] == []


def test_review_after_ready_evaluation_conflicts(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)
    evaluate(authenticated_client, application_id)

    response = authenticated_client.post(
        f"{API}/applications/{application_id}{REVIEW_URL}",
        json={
            "decisions": [{"field_name": "iban", "decision": "VERIFIED"}],
        },
    )
    assert response.status_code == 409
    assert "already" in response.json()["detail"]


def test_review_without_evaluation_rejected(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)
    response = authenticated_client.post(
        f"{API}/applications/{application_id}{REVIEW_URL}",
        json={
            "decisions": [{"field_name": "iban", "decision": "VERIFIED"}],
        },
    )
    assert response.status_code == 422


def test_review_unknown_field_rejected(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    evaluate(authenticated_client, application_id)

    response = authenticated_client.post(
        f"{API}/applications/{application_id}{REVIEW_URL}",
        json={
            "decisions": [{"field_name": "unknown_field", "decision": "VERIFIED"}],
        },
    )
    assert response.status_code == 422
    assert "not flagged" in response.json()["detail"]


def test_review_missing_field_rejected(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]
    decisions = [
        (field["field_name"], "VERIFIED", None)
        for field in flagged
        if field["field_name"] != "iban"
    ]
    response = authenticated_client.post(
        f"{API}/applications/{application_id}{REVIEW_URL}",
        json={"decisions": _decisions(decisions)},
    )
    assert response.status_code == 422
    assert "missing decisions" in response.json()["detail"].lower()


def test_review_corrected_without_value_rejected(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]
    decisions = _verified_decisions(flagged, {"iban"})
    decisions.append(("iban", "CORRECTED", None))

    response = authenticated_client.post(
        f"{API}/applications/{application_id}{REVIEW_URL}",
        json={"decisions": _decisions(decisions)},
    )
    assert response.status_code == 422
    assert "corrected value" in response.json()["detail"].lower()


def test_review_already_applied_conflict(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]
    decisions = [
        (field["field_name"], "VERIFIED", None) for field in flagged
    ]
    review(authenticated_client, application_id, _decisions(decisions))

    response = authenticated_client.post(
        f"{API}/applications/{application_id}{REVIEW_URL}",
        json={
            "decisions": [{"field_name": "iban", "decision": "VERIFIED"}],
        },
    )
    assert response.status_code == 409


# --- Persistence & audit -----------------------------------------------------


def test_audit_log_records_full_flow(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    evaluate(authenticated_client, application_id)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]
    decisions = _verified_decisions(flagged, {"iban"})
    decisions.append(("iban", "CANNOT_VERIFY", None))
    review(authenticated_client, application_id, _decisions(decisions))

    actions = audit_actions(application_id)
    assert actions.count("confidence.evaluated") == 2
    assert actions.count("confidence.field_verified") == len(flagged) - 1
    assert "confidence.field_cannot_verify" in actions
    assert "confidence.reviewed" in actions
    assert "confidence.processing_halted" in actions


def test_extracted_fields_table_has_confidence_columns():
    columns = {
        column["name"] for column in inspect(engine).get_columns("extracted_fields")
    }
    assert {
        "confidence_score",
        "confidence_source",
        "confidence_reason",
        "verification_status",
        "human_corrected_value",
        "human_verified",
        "reviewer",
        "reviewed_at",
        "normalized_value",
    }.issubset(columns)
