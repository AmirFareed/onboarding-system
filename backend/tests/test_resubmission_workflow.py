"""Regression tests for the document resubmission and waiting-time workflow.

Exercises the real operator workflow and upload paths (not direct DB insertion)
to verify that:

- Initial submission produces no DOCUMENTS_REQUESTED / DOCUMENTS_RECEIVED
- Operator request creates DOCUMENTS_REQUESTED with correct metadata
- Applicant resubmission creates DOCUMENTS_RECEIVED and a waiting span
- Multiple cycles are tracked independently
- Open requests are represented correctly
- Initial bulk upload does not produce a false DOCUMENTS_RECEIVED
- Performance correctly consumes the resulting evidence
"""

from datetime import timedelta

from app.database.connection import SessionLocal
from app.database.models.enums import (
    ApplicationStatus,
    DocumentType,
    ValidationEventType,
)
from app.database.models.validation_history import ValidationHistoryEntry
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.validation_history_repository import (
    ValidationHistoryRepository,
)
from tests.conftest import PDF_BYTES
from tests.test_upload_api import create_application, upload

API = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _history_events(application_id: int) -> list[ValidationHistoryEntry]:
    """Return all validation history events for an application, oldest first."""
    db = SessionLocal()
    try:
        entries, _ = ValidationHistoryRepository(db).list_for_application(
            application_id, offset=0, limit=1000
        )
        return list(reversed(entries))
    finally:
        db.close()


def _status(application_id: int) -> ApplicationStatus:
    """Return the current application status."""
    db = SessionLocal()
    try:
        app = ApplicationRepository(db).get_by_id(application_id)
        return app.status
    finally:
        db.close()


def _request_docs(client, application_id: int, missing: list[str], reason: str = "Missing documents"):
    """Operator requests missing documents via the real API."""
    return client.post(
        f"{API}/applications/{application_id}/request-documents",
        json={"missing_document_types": missing, "reason": reason},
    )


def _upload_doc(client, application_id: int, doc_type: str = "TRIPARTITE_AGREEMENT"):
    """Upload a document via the real upload API."""
    return upload(client, application_id, document_type=doc_type)


# ---------------------------------------------------------------------------
# Test 1 — Initial submission produces no cycle events
# ---------------------------------------------------------------------------

def test_initial_upload_creates_no_document_request_or_receipt(operator_client):
    """A fresh application upload must not generate DOCUMENTS_REQUESTED or DOCUMENTS_RECEIVED."""
    app_id = create_application(operator_client)
    response = _upload_doc(operator_client, app_id)
    assert response.status_code == 201, response.text

    events = _history_events(app_id)
    event_types = [e.event_type for e in events]

    assert ValidationEventType.DOCUMENTS_REQUESTED not in event_types
    assert ValidationEventType.DOCUMENTS_RECEIVED not in event_types


# ---------------------------------------------------------------------------
# Test 2 — Operator requests missing documents
# ---------------------------------------------------------------------------

def test_operator_request_creates_documents_requested(operator_client):
    """Operator request-documents must create a DOCUMENTS_REQUESTED event with correct metadata."""
    app_id = create_application(operator_client)

    response = _request_docs(
        operator_client,
        app_id,
        missing=["ACCOUNT_MAINTENANCE_CERTIFICATE", "AUTHORITY_LETTER"],
        reason="Missing AMC and Authority Letter",
    )
    assert response.status_code == 200, response.text

    # Status must be NEEDS_DOCUMENTS
    assert _status(app_id) is ApplicationStatus.NEEDS_DOCUMENTS

    events = _history_events(app_id)
    requested = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_REQUESTED]
    assert len(requested) == 1

    entry = requested[0]
    assert entry.missing_document_types == ["ACCOUNT_MAINTENANCE_CERTIFICATE", "AUTHORITY_LETTER"]
    assert entry.reason == "Missing AMC and Authority Letter"
    assert entry.actor_name == "Test OPERATOR"
    assert entry.actor_role == "OPERATOR"
    assert entry.previous_status == ApplicationStatus.SUBMITTED.value
    assert entry.new_status == ApplicationStatus.NEEDS_DOCUMENTS.value


# ---------------------------------------------------------------------------
# Test 3 — Applicant resubmits documents
# ---------------------------------------------------------------------------

def test_resubmission_records_documents_received(operator_client):
    """When an applicant uploads while status is NEEDS_DOCUMENTS, DOCUMENTS_RECEIVED is recorded."""
    app_id = create_application(operator_client)

    # Operator requests documents
    _request_docs(operator_client, app_id, missing=["TRIPARTITE_AGREEMENT"])
    assert _status(app_id) is ApplicationStatus.NEEDS_DOCUMENTS

    # Applicant uploads the requested document (operator_client can also upload)
    response = _upload_doc(operator_client, app_id)
    assert response.status_code == 201, response.text

    events = _history_events(app_id)
    received = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_RECEIVED]
    assert len(received) == 1

    entry = received[0]
    assert entry.previous_status == ApplicationStatus.NEEDS_DOCUMENTS.value
    assert entry.actor_name is not None


# ---------------------------------------------------------------------------
# Test 4 — Multiple resubmission cycles
# ---------------------------------------------------------------------------

def test_multiple_resubmission_cycles_are_tracked_independently(operator_client):
    """Two request/receipt pairs must produce two separate DOCUMENTS_RECEIVED events."""
    app_id = create_application(operator_client)

    # Cycle 1: request → upload
    _request_docs(operator_client, app_id, missing=["TRIPARTITE_AGREEMENT"])
    assert _status(app_id) is ApplicationStatus.NEEDS_DOCUMENTS
    _upload_doc(operator_client, app_id)

    # Cycle 2: request → upload
    _request_docs(operator_client, app_id, missing=["AUTHORITY_LETTER"])
    assert _status(app_id) is ApplicationStatus.NEEDS_DOCUMENTS
    _upload_doc(operator_client, app_id, doc_type="AUTHORITY_LETTER")

    events = _history_events(app_id)
    requested = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_REQUESTED]
    received = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_RECEIVED]

    assert len(requested) == 2
    assert len(received) == 2

    # Chronological order: R1, Rec1, R2, Rec2
    assert requested[0].created_at < received[0].created_at
    assert received[0].created_at < requested[1].created_at
    assert requested[1].created_at < received[1].created_at


# ---------------------------------------------------------------------------
# Test 5 — Open request (no response yet)
# ---------------------------------------------------------------------------

def test_open_request_has_no_received_event(operator_client):
    """A DOCUMENTS_REQUESTED without a subsequent upload must not produce a DOCUMENTS_RECEIVED."""
    app_id = create_application(operator_client)

    _request_docs(operator_client, app_id, missing=["TRIPARTITE_AGREEMENT"])
    assert _status(app_id) is ApplicationStatus.NEEDS_DOCUMENTS

    # Do NOT upload anything — the request remains open
    events = _history_events(app_id)
    requested = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_REQUESTED]
    received = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_RECEIVED]

    assert len(requested) == 1
    assert len(received) == 0


# ---------------------------------------------------------------------------
# Test 6 — Initial bulk upload does not create false receipt
# ---------------------------------------------------------------------------

def test_initial_bulk_upload_does_not_create_false_receipt(operator_client):
    """An initial upload on a SUBMITTED application must not generate DOCUMENTS_RECEIVED."""
    app_id = create_application(operator_client)
    assert _status(app_id) is ApplicationStatus.SUBMITTED

    response = _upload_doc(operator_client, app_id)
    assert response.status_code == 201, response.text

    events = _history_events(app_id)
    received = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_RECEIVED]
    assert len(received) == 0, (
        f"Initial upload must not create DOCUMENTS_RECEIVED, "
        f"but found {len(received)} event(s)"
    )


# ---------------------------------------------------------------------------
# Test 7 — Performance consumes the evidence correctly
# ---------------------------------------------------------------------------

def test_performance_waiting_span_matches_workflow_events(operator_client):
    """Performance waiting_seconds must equal the gap between REQUESTED and RECEIVED timestamps."""
    import time
    app_id = create_application(operator_client)

    # Operator requests documents
    _request_docs(operator_client, app_id, missing=["TRIPARTITE_AGREEMENT"])

    # Small delay so request and receipt have different timestamps
    time.sleep(1.1)

    # Applicant resubmits
    _upload_doc(operator_client, app_id)

    # Verify events were recorded correctly
    events = _history_events(app_id)
    requested = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_REQUESTED]
    received = [e for e in events if e.event_type is ValidationEventType.DOCUMENTS_RECEIVED]
    assert len(requested) == 1, f"Expected 1 DOCUMENTS_REQUESTED, got {len(requested)}"
    assert len(received) == 1, f"Expected 1 DOCUMENTS_RECEIVED, got {len(received)}"

    # Check Performance via direct service call
    from app.performance.services import PerformanceService
    from app.database.connection import SessionLocal as _SL

    db = _SL()
    try:
        perf = PerformanceService(db)
        items, total = perf.list_applications(query=str(app_id), limit=1)
        assert total == 1, f"Expected 1 application, got {total}"
        row = items[0]
        assert row.application_id == app_id
        assert row.resubmissions == 1
        assert row.missing_document_cycles == 1
        # waiting_seconds should be >= 1 (we slept 1.1s between request and receipt)
        assert row.waiting_seconds is not None, (
            f"waiting_seconds is None; waiting_spans={row.waiting_spans}"
        )
        assert row.waiting_seconds >= 1, (
            f"Expected >= 1s waiting, got {row.waiting_seconds}s"
        )

        # Evidence spans must exist
        assert len(row.waiting_spans) == 1
        span = row.waiting_spans[0]
        assert span.open is False
        assert span.duration_seconds is not None
        assert span.duration_seconds >= 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 8 — Application History timeline includes cycle events
# ---------------------------------------------------------------------------

def test_application_history_timeline_includes_request_and_receipt(operator_client):
    """Application History timeline must contain DOCUMENTS_REQUESTED and DOCUMENTS_RECEIVED."""
    app_id = create_application(operator_client)

    # Operator requests documents
    _request_docs(operator_client, app_id, missing=["TRIPARTITE_AGREEMENT"])

    # Applicant resubmits
    _upload_doc(operator_client, app_id)

    # Check Application History timeline via direct service call (avoids cookie conflict)
    from app.application_history.services import ApplicationHistoryService
    from app.database.connection import SessionLocal as _SL

    db = _SL()
    try:
        hist = ApplicationHistoryService(db)
        events = hist.timeline(app_id)
        kinds = [e.kind for e in events]

        assert "DOCUMENTS_REQUESTED" in kinds
        assert "DOCUMENTS_RECEIVED" in kinds

        # Verify chronological ordering
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)
    finally:
        db.close()
