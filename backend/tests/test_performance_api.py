"""Tests for the IT Performance API.

The Performance API is a read-only, IT-only view of application turnaround
timing. Timing is evidence-backed: every metric derives from timestamps the
system itself recorded (queue job runs, document request/receipt events, review
decisions), and every per-application row carries the individual spans behind
its numbers. Tests cover the IT-only guard, the aggregate overview, the
per-application breakdown, open (unanswered) document-request spans, and the
"zero vs. not enough data" empty-state behavior.
"""

from datetime import datetime, timedelta, timezone

from app.database.connection import SessionLocal
from app.database.models.enums import (
    ApplicationStatus,
    JobStatus,
    JobType,
    ReviewDecision,
    ValidationEventType,
)
from app.database.repositories.application_repository import ApplicationRepository
from tests.test_application_history_api import (
    _add_document,
    _add_queue_job,
    _add_review,
    _add_validation_event,
    _set_status,
    _set_submitted_at,
)
from tests.test_technical_validation_api import create_application_direct

API = "/api/v1"

OVERVIEW_URL = "/performance/overview"
APPLICATIONS_URL = "/performance/applications"

SECONDS_PER_HOUR = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Role enforcement -------------------------------------------------------


def test_performance_require_it_role(reviewer_client):
    assert reviewer_client.get(f"{API}{OVERVIEW_URL}").status_code == 403
    assert reviewer_client.get(f"{API}{APPLICATIONS_URL}").status_code == 403


def test_performance_require_it_role_for_operator(operator_client):
    assert operator_client.get(f"{API}{OVERVIEW_URL}").status_code == 403
    assert operator_client.get(f"{API}{APPLICATIONS_URL}").status_code == 403


def test_performance_rejects_employee_superuser(employee_client):
    assert employee_client.get(f"{API}{OVERVIEW_URL}").status_code == 403
    assert employee_client.get(f"{API}{APPLICATIONS_URL}").status_code == 403


def test_performance_require_authentication(client):
    assert client.get(f"{API}{OVERVIEW_URL}").status_code == 401
    assert client.get(f"{API}{APPLICATIONS_URL}").status_code == 401


# --- Overview ---------------------------------------------------------------


def test_overview_empty_returns_zero_counts_no_misleading_averages(it_client):
    response = it_client.get(f"{API}{OVERVIEW_URL}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_applications"] == 0
    assert payload["decided_applications"] == 0
    assert payload["status_counts"] == {}
    assert payload["avg_waiting_seconds"] is None
    assert payload["avg_processing_seconds"] is None
    assert payload["avg_review_seconds"] is None
    assert payload["avg_turnaround_seconds"] is None
    assert payload["total_resubmissions"] == 0
    assert payload["total_missing_document_cycles"] == 0


def test_overview_averages_only_over_applications_that_have_the_metric(it_client):
    t = _now()

    # Decided application with full lifecycle timing.
    decided_id = create_application_direct()
    _set_status(decided_id, ApplicationStatus.APPROVED)
    _set_submitted_at(decided_id, t - timedelta(hours=49))
    _add_validation_event(
        application_id=decided_id,
        event_type=ValidationEventType.DOCUMENTS_REQUESTED,
        created_at=t - timedelta(hours=48),
        new_status=ApplicationStatus.NEEDS_DOCUMENTS.value,
    )
    _add_validation_event(
        application_id=decided_id,
        event_type=ValidationEventType.DOCUMENTS_RECEIVED,
        created_at=t - timedelta(hours=40),
        new_status=ApplicationStatus.SUBMITTED.value,
    )
    _add_queue_job(
        application_id=decided_id,
        job_type=JobType.DOCUMENT_OCR,
        status=JobStatus.COMPLETED,
        created_at=t - timedelta(hours=36),
        started_at=t - timedelta(hours=36),
        completed_at=t - timedelta(hours=35),
    )
    _add_queue_job(
        application_id=decided_id,
        job_type=JobType.APPLICATION_PIPELINE,
        status=JobStatus.COMPLETED,
        created_at=t - timedelta(hours=34),
        started_at=t - timedelta(hours=34),
        completed_at=t - timedelta(hours=33),
    )
    _add_review(
        application_id=decided_id,
        decision=ReviewDecision.APPROVE,
        reviewed_at=t - timedelta(hours=30),
    )

    # In-flight application with no decision and no processing yet.
    in_flight_id = create_application_direct()
    _set_status(in_flight_id, ApplicationStatus.SUBMITTED)

    response = it_client.get(f"{API}{OVERVIEW_URL}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_applications"] == 2
    assert payload["decided_applications"] == 1
    assert payload["status_counts"] == {"APPROVED": 1, "SUBMITTED": 1}

    # Waiting: 48h - 40h = 8h = 28800s.
    assert payload["avg_waiting_seconds"] == 8 * SECONDS_PER_HOUR
    # Processing: DOCUMENT_OCR (1h) + pipeline (1h) = 2h = 7200s.
    assert payload["avg_processing_seconds"] == 2 * SECONDS_PER_HOUR
    # Review: pipeline completion (t-33h) -> decision (t-30h) = 3h = 10800s.
    assert payload["avg_review_seconds"] == 3 * SECONDS_PER_HOUR
    # Turnaround: submitted (t-49h app created) -> decision (t-30h) = 19h.
    assert payload["avg_turnaround_seconds"] == 19 * SECONDS_PER_HOUR

    assert payload["total_resubmissions"] == 1
    assert payload["total_missing_document_cycles"] == 1


# --- Per-application breakdown ---------------------------------------------


def test_application_breakdown_reports_evidence_spans(it_client):
    app_id = create_application_direct()
    t = _now()
    _set_status(app_id, ApplicationStatus.APPROVED)
    _set_submitted_at(app_id, t - timedelta(hours=11))
    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.DOCUMENTS_REQUESTED,
        created_at=t - timedelta(hours=10),
        new_status=ApplicationStatus.NEEDS_DOCUMENTS.value,
    )
    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.DOCUMENTS_RECEIVED,
        created_at=t - timedelta(hours=8),
        new_status=ApplicationStatus.SUBMITTED.value,
    )
    _add_queue_job(
        application_id=app_id,
        job_type=JobType.DOCUMENT_OCR,
        status=JobStatus.COMPLETED,
        created_at=t - timedelta(hours=6),
        started_at=t - timedelta(hours=6),
        completed_at=t - timedelta(hours=5),
    )
    _add_queue_job(
        application_id=app_id,
        job_type=JobType.APPLICATION_PIPELINE,
        status=JobStatus.COMPLETED,
        created_at=t - timedelta(hours=4),
        started_at=t - timedelta(hours=4),
        completed_at=t - timedelta(hours=3),
    )
    _add_review(
        application_id=app_id,
        decision=ReviewDecision.REJECT,
        reviewed_at=t - timedelta(hours=2),
        reviewer_name="Test Reviewer",
        comments="Rejected after review",
    )

    response = it_client.get(f"{API}{APPLICATIONS_URL}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    row = payload["items"][0]
    assert row["application_id"] == app_id
    assert row["status"] == "APPROVED"

    # Waiting: 10h - 8h = 2h = 7200s.
    assert row["waiting_seconds"] == 2 * SECONDS_PER_HOUR
    assert len(row["waiting_spans"]) == 1
    waiting_span = row["waiting_spans"][0]
    assert waiting_span["open"] is False
    assert waiting_span["duration_seconds"] == 2 * SECONDS_PER_HOUR

    # Processing: 1h (OCR) + 1h (pipeline) = 2h = 7200s.
    assert row["processing_seconds"] == 2 * SECONDS_PER_HOUR
    assert len(row["processing_spans"]) == 2

    # Review: pipeline completion (t-3h) -> decision (t-2h) = 1h = 3600s.
    assert row["review_seconds"] == SECONDS_PER_HOUR
    assert len(row["review_spans"]) == 1
    assert row["review_spans"][0]["detail"] == "Decision: REJECT"

    # Turnaround: created (t-11h) -> decision (t-2h) = 9h = 32400s.
    assert row["total_turnaround_seconds"] == 9 * SECONDS_PER_HOUR
    assert row["resubmissions"] == 1
    assert row["missing_document_cycles"] == 1


def test_unmatched_document_request_is_open_span_not_closed_time(it_client):
    """A bulk upload that never records DOCUMENTS_RECEIVED must not be counted
    as closed waiting time -- it stays an open span for the evidence view."""
    app_id = create_application_direct()
    t = _now()
    _set_status(app_id, ApplicationStatus.PROCESSING)
    _add_validation_event(
        application_id=app_id,
        event_type=ValidationEventType.DOCUMENTS_REQUESTED,
        created_at=t - timedelta(days=2),
        new_status=ApplicationStatus.NEEDS_DOCUMENTS.value,
    )
    # No DOCUMENTS_RECEIVED -- the bulk path transitions straight to PROCESSING.
    _add_queue_job(
        application_id=app_id,
        job_type=JobType.DOCUMENT_OCR,
        status=JobStatus.PROCESSING,
        created_at=t - timedelta(hours=1),
        started_at=t - timedelta(hours=1),
        completed_at=None,
    )

    response = it_client.get(f"{API}{APPLICATIONS_URL}")
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["waiting_seconds"] is None
    assert len(row["waiting_spans"]) == 1
    waiting_span = row["waiting_spans"][0]
    assert waiting_span["open"] is True
    assert waiting_span["end"] is None
    assert waiting_span["duration_seconds"] is None
    assert "waiting" in waiting_span["detail"].lower()

    # Processing is still open (job running) so it is not counted as closed.
    assert row["processing_seconds"] is None
    assert len(row["processing_spans"]) == 1
    assert row["processing_spans"][0]["open"] is True

    # No decision -> no closed turnaround.
    assert row["total_turnaround_seconds"] is None
    assert row["decided_at"] is None


def test_processing_duration_uses_claimed_at_not_heartbeat_drifted_started_at(
    it_client,
):
    """Long-running jobs must report their real duration, not just the tail
    since the last liveness heartbeat.

    Regression test for the 2026-08-24 finding: a real ~46-minute bulk-split
    job reported a small fraction of that in processing_seconds, because
    QueueJobRepository.heartbeat() repeatedly overwrites started_at while a
    worker holds a job (so it stays live under stale-job recovery), leaving
    started_at reflecting only the last heartbeat rather than when the job
    was actually claimed. claimed_at is set once per claim and never
    touched by the heartbeat, so it is the correct span start.
    """
    app_id = create_application_direct()
    t = _now()
    _set_status(app_id, ApplicationStatus.PROCESSING)
    _add_queue_job(
        application_id=app_id,
        job_type=JobType.DOCUMENT_OCR,
        status=JobStatus.COMPLETED,
        created_at=t - timedelta(minutes=46),
        # started_at was drifted forward by repeated heartbeats during the
        # long OCR pass -- only 90 seconds "old" by completion time.
        started_at=t - timedelta(seconds=90),
        claimed_at=t - timedelta(minutes=46),
        completed_at=t,
    )

    response = it_client.get(f"{API}{APPLICATIONS_URL}")
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]

    assert row["processing_seconds"] == 46 * 60
    assert len(row["processing_spans"]) == 1
    assert row["processing_spans"][0]["duration_seconds"] == 46 * 60


def test_processing_duration_falls_back_to_started_at_without_claimed_at(it_client):
    """Rows written before claimed_at existed must not silently vanish from
    the report -- they fall back to the pre-existing started_at behavior."""
    app_id = create_application_direct()
    t = _now()
    _set_status(app_id, ApplicationStatus.PROCESSING)
    _add_queue_job(
        application_id=app_id,
        job_type=JobType.DOCUMENT_OCR,
        status=JobStatus.COMPLETED,
        created_at=t - timedelta(hours=1),
        started_at=t - timedelta(hours=1),
        completed_at=t - timedelta(minutes=30),
    )

    response = it_client.get(f"{API}{APPLICATIONS_URL}")
    assert response.status_code == 200, response.text
    row = response.json()["items"][0]

    assert row["processing_seconds"] == 30 * 60


def test_application_performance_search_and_pagination(it_client):
    for _ in range(3):
        create_application_direct()
    response = it_client.get(f"{API}{APPLICATIONS_URL}?offset=1&limit=1")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 1
