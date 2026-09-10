"""Tests for the IT Application History API.

The Application History API is a read-only, IT-only projection of the existing
application lifecycle data (applications, documents, validation history, queue
jobs, human reviews). Tests cover the IT-only role guard, the paginated list
with search/status filters, and the merged per-application timeline.
"""

from datetime import datetime, timedelta, timezone

from app.database.connection import SessionLocal
from app.database.models.application import Application
from app.database.models.document import Document
from app.database.models.enums import (
    ApplicationStatus,
    DocumentType,
    JobStatus,
    JobType,
    ReviewDecision,
    ValidationEventType,
)
from app.database.models.human_review import HumanReview
from app.database.models.queue_job import QueueJob
from app.database.models.validation_history import ValidationHistoryEntry
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.human_review_repository import HumanReviewRepository
from app.database.repositories.validation_history_repository import (
    ValidationHistoryRepository,
)
from tests.test_technical_validation_api import create_application_direct

API = "/api/v1"

HISTORY_URL = "/applications/history"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _add_validation_event(
    *,
    application_id: int,
    event_type: ValidationEventType,
    created_at: datetime,
    actor_name: str = "Test Operator",
    actor_role: str = "OPERATOR",
    previous_status: str = "SUBMITTED",
    new_status: str | None = None,
    missing_document_types: list[str] | None = None,
    reason: str | None = None,
) -> None:
    """Append a validation-history event with a controlled timestamp."""
    db = SessionLocal()
    try:
        ValidationHistoryRepository(db).create(
            application_id=application_id,
            event_type=event_type,
            actor_name=actor_name,
            actor_role=actor_role,
            previous_status=previous_status,
            new_status=new_status,
            missing_document_types=missing_document_types,
            reason=reason,
        )
        # Override the server-default timestamp so the test controls the clock.
        entry = db.query(ValidationHistoryEntry).filter_by(
            application_id=application_id, event_type=event_type
        ).order_by(ValidationHistoryEntry.id.desc()).first()
        entry.created_at = created_at
        db.commit()
    finally:
        db.close()


def _add_document(
    *, application_id: int, uploaded_at: datetime, document_type: DocumentType = DocumentType.ONE_LINK_LETTER
) -> None:
    """Insert a document row with a controlled upload timestamp."""
    db = SessionLocal()
    try:
        db.add(
            Document(
                application_id=application_id,
                document_type=document_type,
                copy_number=1,
                original_filename="sample.pdf",
                stored_file_path=f"apps/{application_id}/sample.pdf",
                file_type="application/pdf",
            )
        )
        db.flush()
        doc = db.query(Document).filter_by(application_id=application_id).order_by(Document.id.desc()).first()
        doc.uploaded_at = uploaded_at
        db.commit()
    finally:
        db.close()


def _add_queue_job(
    *,
    application_id: int,
    job_type: JobType,
    status: JobStatus,
    created_at: datetime,
    started_at: datetime | None,
    completed_at: datetime | None,
    document_id: int | None = None,
    claimed_at: datetime | None = None,
) -> None:
    """Insert a queue job with fully controlled timestamps.

    ``claimed_at`` defaults to unset (``None``), matching how most tests
    don't care about the started_at/claimed_at distinction -- the
    performance report falls back to ``started_at`` when ``claimed_at`` is
    absent. Pass it explicitly to simulate a job whose ``started_at`` has
    drifted forward from a liveness heartbeat, as a real long-running bulk
    job's does.
    """
    db = SessionLocal()
    try:
        db.add(
            QueueJob(
                application_id=application_id,
                document_id=document_id,
                job_type=job_type,
                status=status,
                created_at=created_at,
                started_at=started_at,
                claimed_at=claimed_at,
                completed_at=completed_at,
            )
        )
        db.commit()
    finally:
        db.close()


def _add_review(
    *,
    application_id: int,
    decision: ReviewDecision,
    reviewed_at: datetime,
    reviewer_name: str = "Test Reviewer",
    comments: str | None = None,
) -> None:
    """Insert a human review with a controlled timestamp."""
    db = SessionLocal()
    try:
        HumanReviewRepository(db).create(
            application_id=application_id,
            reviewer_name=reviewer_name,
            decision=decision,
            comments=comments,
        )
        review = db.query(HumanReview).filter_by(application_id=application_id).order_by(HumanReview.id.desc()).first()
        review.reviewed_at = reviewed_at
        db.commit()
    finally:
        db.close()


def _set_status(application_id: int, status: ApplicationStatus) -> None:
    """Set an application's status directly."""
    db = SessionLocal()
    try:
        ApplicationRepository(db).update(
            db.get(Application, application_id),
            status=status,
        )
    finally:
        db.close()


def _set_submitted_at(application_id: int, submitted_at: datetime) -> None:
    """Override the application's creation timestamp so tests control the clock."""
    db = SessionLocal()
    try:
        app = db.get(Application, application_id)
        app.submitted_at = submitted_at
        db.commit()
    finally:
        db.close()


# --- Role enforcement -------------------------------------------------------


def test_application_history_require_it_role(reviewer_client):
    response = reviewer_client.get(f"{API}{HISTORY_URL}")
    assert response.status_code == 403, response.text


def test_application_history_require_it_role_for_operator(operator_client):
    response = operator_client.get(f"{API}{HISTORY_URL}")
    assert response.status_code == 403, response.text


def test_application_history_rejects_employee_superuser(employee_client):
    response = employee_client.get(f"{API}{HISTORY_URL}")
    assert response.status_code == 403, response.text


def test_application_history_require_authentication(client):
    response = client.get(f"{API}{HISTORY_URL}")
    assert response.status_code == 401, response.text


def test_application_timeline_require_it_role(reviewer_client):
    response = reviewer_client.get(f"{API}/applications/1/timeline")
    assert response.status_code == 403, response.text


def test_application_timeline_rejects_employee_superuser(employee_client):
    response = employee_client.get(f"{API}/applications/1/timeline")
    assert response.status_code == 403, response.text


def test_application_timeline_require_authentication(client):
    response = client.get(f"{API}/applications/1/timeline")
    assert response.status_code == 401, response.text


# --- List -------------------------------------------------------------------


def test_history_lists_applications_with_last_event(it_client):
    app_id = create_application_direct()
    t = _now()
    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.DOCUMENTS_REQUESTED,
        created_at=t - timedelta(hours=2),
        new_status=ApplicationStatus.NEEDS_DOCUMENTS.value,
        missing_document_types=["ONE_LINK_LETTER"],
        reason="Missing 1-Link form",
    )
    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.DOCUMENTS_RECEIVED,
        created_at=t - timedelta(hours=1),
        new_status=ApplicationStatus.SUBMITTED.value,
    )

    response = it_client.get(f"{API}{HISTORY_URL}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["application_id"] == app_id
    assert item["last_event_type"] == "DOCUMENTS_RECEIVED"
    assert item["last_event_at"] is not None


def test_history_last_event_prefers_latest_of_uploads_and_reviews(it_client):
    app_id = create_application_direct()
    t = _now()
    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.DOCUMENTS_RECEIVED,
        created_at=t - timedelta(days=3),
    )
    _add_document(application_id=app_id, uploaded_at=t - timedelta(days=2))
    _add_review(
        application_id=app_id,
        decision=ReviewDecision.APPROVE,
        reviewed_at=t - timedelta(hours=1),
    )

    response = it_client.get(f"{API}{HISTORY_URL}")
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["last_event_type"] == "REVIEW_APPROVED"


def test_history_search_by_id(it_client):
    app_id = create_application_direct()
    response = it_client.get(f"{API}{HISTORY_URL}?query={app_id}")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["application_id"] == app_id


def test_history_search_by_name(it_client):
    app_id = create_application_direct()
    db = SessionLocal()
    try:
        app = ApplicationRepository(db).get_by_id(app_id)
        app.name = "TMA Khal Dir Lower"
        db.commit()
    finally:
        db.close()
    response = it_client.get(f"{API}{HISTORY_URL}?query=TMA")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["application_name"] == "TMA Khal Dir Lower"


def test_history_search_by_creator(it_client):
    app_id = create_application_direct()
    db = SessionLocal()
    try:
        app = ApplicationRepository(db).get_by_id(app_id)
        app.created_by = "ops.lead"
        db.commit()
    finally:
        db.close()
    response = it_client.get(f"{API}{HISTORY_URL}?query=ops.lead")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1


def test_history_filters_by_status(it_client):
    pending_id = create_application_direct()
    _set_status(pending_id, ApplicationStatus.PENDING_REVIEW)
    approved_id = create_application_direct()
    _set_status(approved_id, ApplicationStatus.APPROVED)

    response = it_client.get(f"{API}{HISTORY_URL}?status=APPROVED")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["application_id"] == approved_id


def test_history_pagination(it_client):
    for _ in range(3):
        create_application_direct()
    response = it_client.get(f"{API}{HISTORY_URL}?offset=1&limit=1")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 1


def test_history_empty(it_client):
    response = it_client.get(f"{API}{HISTORY_URL}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 0
    assert payload["items"] == []


# --- Timeline ---------------------------------------------------------------


def test_timeline_merges_all_event_sources(it_client):
    app_id = create_application_direct()
    t = _now()
    _set_status(app_id, ApplicationStatus.PENDING_REVIEW)
    _set_submitted_at(app_id, t - timedelta(days=5))

    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.DOCUMENTS_REQUESTED,
        created_at=t - timedelta(days=4),
        new_status=ApplicationStatus.NEEDS_DOCUMENTS.value,
        missing_document_types=["ONE_LINK_LETTER"],
        reason="Need the 1-Link form",
    )
    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.DOCUMENTS_RECEIVED,
        created_at=t - timedelta(days=3),
        new_status=ApplicationStatus.SUBMITTED.value,
    )
    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.SUBMITTED_FOR_PROCESSING,
        created_at=t - timedelta(days=2),
        previous_status=ApplicationStatus.SUBMITTED.value,
        new_status=ApplicationStatus.PROCESSING.value,
    )
    _add_document(application_id=app_id, uploaded_at=t - timedelta(days=3))
    _add_queue_job(
        application_id=app_id,
        job_type=JobType.APPLICATION_PIPELINE,
        status=JobStatus.COMPLETED,
        created_at=t - timedelta(days=2),
        started_at=t - timedelta(days=2),
        completed_at=t - timedelta(hours=20),
    )
    _add_review(
        application_id=app_id,
        decision=ReviewDecision.APPROVE,
        reviewed_at=t - timedelta(hours=2),
        reviewer_name="Test Reviewer",
        comments="All documents verified",
    )

    response = it_client.get(f"{API}/applications/{app_id}/timeline")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["application_id"] == app_id
    kinds = [event["kind"] for event in payload["events"]]
    assert kinds == [
        "APPLICATION_CREATED",
        "DOCUMENTS_REQUESTED",
        "DOCUMENTS_RECEIVED",
        "DOCUMENT_UPLOADED",
        "SUBMITTED_FOR_PROCESSING",
        "PROCESSING_COMPLETED",
        "REVIEW_DECISION",
    ]
    timestamps = [event["timestamp"] for event in payload["events"]]
    assert timestamps == sorted(timestamps)

    review_event = payload["events"][-1]
    assert review_event["actor_name"] == "Test Reviewer"
    assert review_event["detail"] == "All documents verified"


def test_timeline_not_found(it_client):
    response = it_client.get(f"{API}/applications/999999/timeline")
    assert response.status_code == 404, response.text
