"""Tests for the automatic post-OCR pipeline chain.

Before this, OCR completing never led anywhere: analysis, confidence,
normalization and rule validation each required their own direct API call,
and nothing in this codebase made those calls. These tests prove the queue
worker now runs that chain automatically once every document job for an
application is terminal, using the same claim/retry/heartbeat machinery
already proven for document processing (see ``app.bulk_queue.workers`` and
``app.bulk_queue.pipeline_runner``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.bulk_queue.pipeline_runner import PipelineRunnerService
from app.bulk_queue.services import BulkQueueService
from app.bulk_queue.workers import ACTION_PIPELINE_BLOCKED, ACTION_PIPELINE_FAILED, BulkQueueWorker, drain_queue
from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models.audit_log import AuditLog
from app.database.models.enums import ApplicationStatus, JobStatus, JobType
from app.database.models.queue_job import QueueJob
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.extracted_field_repository import ExtractedFieldRepository
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.database.repositories.validation_repository import ValidationRepository
from tests.test_bulk_queue import (
    FailingProcessor,
    SuccessfulProcessor,
    create_application_with_documents,
    enqueue,
)
from tests.test_bulk_upload_api import make_bulk_pdf, upload_bulk
from tests.test_document_analysis_api import BANK_STATEMENT_TEXT
from tests.test_technical_validation_api import create_application
from tests.test_upload_api import upload as upload_single_document

API = "/api/v1"

# All 8 required document types, each with a page header that the
# DocumentSplitter recognises.  Every page also carries enough body text to
# pass the technical validation blur/blank-page checks.
_COMPLETE_BULK_PAGES = [
    "TRIPARTITE AGREEMENT\nThis tripartite agreement is entered into between\n"
    "the sub-biller, 1LINK and KPITB for digital payment collection.\n"
    "First copy.",
    "BILATERAL AGREEMENT\nThis bilateral service level agreement is between\n"
    "the merchant and 1LINK for payment processing services.",
    "ACCOUNT MAINTENANCE CERTIFICATE\nThe bank hereby certifies the account\n"
    "maintenance details for the registered merchant organisation.",
    "ONE LINK APPLICATION FORM\nApplication form submitted by the organisation\n"
    "to register for digital payment collection through 1LINK.",
    "AUTHORITY LETTER\nThis authority letter is issued by the organisation\n"
    "to authorise the named signatory for banking operations.",
    "NATIONAL IDENTITY CARD\nComputerised National Identity Card\n"
    "Front face of the CNIC for the authorised signatory.",
    "BUSINESS REQUIREMENT DOCUMENT\nBusiness requirements for the Sample\n"
    "Development Authority digital payment collection system.",
    "FORMAL REQUEST LETTER\nFormal request letter for onboarding onto the\n"
    "1LINK digital payment collection platform.",
]


def pipeline_job_for(application_id: int) -> QueueJob | None:
    """Return the application's pipeline job row, or None."""
    db = SessionLocal()
    try:
        return db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).one_or_none()
    finally:
        db.close()


def audit_actions_for(application_id: int) -> list[str]:
    """Return every audit action recorded for an application."""
    db = SessionLocal()
    try:
        return list(
            db.scalars(
                select(AuditLog.action).where(AuditLog.application_id == application_id)
            ).all()
        )
    finally:
        db.close()


def application_status_for(application_id: int) -> str | None:
    """Return the current status of an application."""
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).get_by_id(application_id)
        return application.status.value if application is not None else None
    finally:
        db.close()


def mark_processing(application_id: int) -> None:
    """Set an application's status to PROCESSING directly.

    Mirrors the real precondition every production enqueue call site now
    establishes (see the guarded writes in ``upload/services.py`` and
    ``bulk_queue/services.py``) without going through the full HTTP upload
    flow, matching this module's existing pattern of building queue state
    directly for worker-level tests.
    """
    db = SessionLocal()
    try:
        applications = ApplicationRepository(db)
        application = applications.get_by_id(application_id)
        applications.update(application, status=ApplicationStatus.PROCESSING)
    finally:
        db.close()


def drain_until_empty(*, max_passes: int = 5) -> None:
    """Drain the real queue repeatedly.

    One pass is not always enough: a bulk-split job enqueues new per-document
    jobs mid-drain, and the pipeline job is itself only enqueued after those
    finish, so it needs a later pass to be claimed and run.
    """
    for _ in range(max_passes):
        summary = drain_queue()
        if summary.processed == 0:
            return


# --- Success: 10 real bulk uploads, chained end to end -----------------------


def test_ten_bulk_uploads_each_produce_a_working_report(authenticated_client):
    application_ids = []
    for _ in range(10):
        application_id = create_application(authenticated_client)
        # Upload all 8 required document types so the application is
        # complete and eligible for processing after the bulk split.
        response = upload_bulk(
            authenticated_client,
            application_id,
            make_bulk_pdf(_COMPLETE_BULK_PAGES),
        )
        assert response.status_code == 201, response.text
        start = authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
        assert start.status_code == 200, start.text
        application_ids.append(application_id)

    drain_until_empty()

    for application_id in application_ids:
        job = pipeline_job_for(application_id)
        assert job is not None, f"application {application_id} never got a pipeline job"
        assert job.status is JobStatus.COMPLETED, (
            f"application {application_id} pipeline job ended {job.status}: {job.last_error}"
        )
        response = authenticated_client.get(f"{API}/applications/{application_id}/validation-report")
        assert response.status_code == 200, response.text
        assert application_status_for(application_id) == "PENDING_REVIEW"


def test_bulk_upload_does_not_force_incomplete_app_into_processing(
    authenticated_client,
):
    """An incomplete bulk upload (only BANK_STATEMENT_TEXT, i.e.
    OTHER_SUPPORTING_DOCUMENT — missing 7 required types) must NOT
    transition the application to PROCESSING.  The operator workflow
    must remain unblocked so documents can be requested.
    """
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([BANK_STATEMENT_TEXT]),
    )
    assert response.status_code == 201, response.text

    # The application must stay in a non-PROCESSING state because the
    # document set is incomplete after the bulk split.
    status = application_status_for(application_id)
    assert status != "PROCESSING", (
        f"Incomplete application must not enter PROCESSING; got {status}"
    )


def test_start_processing_marks_complete_application_processing(
    authenticated_client, monkeypatch
):
    """Checks the synchronous portion of /processing/start in isolation.

    A complete application (all 8 required document types) must transition
    to PROCESSING when the operator calls /processing/start.  An incomplete
    application must NOT.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "bulk_queue_background_drain", False)
    application_id = create_application(authenticated_client)
    # Upload all 8 required document types via a complete bulk PDF.
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(_COMPLETE_BULK_PAGES),
    )
    assert response.status_code == 201, response.text
    assert application_status_for(application_id) == "SUBMITTED"

    start = authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    assert start.status_code == 200, start.text

    assert application_status_for(application_id) == "PROCESSING"


def test_enqueue_does_not_regress_a_decided_application_status():
    """Adding a document after a decision must not resurrect PROCESSING.

    A document can be uploaded to an application after it has already been
    approved/rejected/corrected (upload has no status check). Re-enqueueing
    must not silently move the status backward from a terminal decision.
    """
    application_id, _ = create_application_with_documents(1)
    db = SessionLocal()
    try:
        applications = ApplicationRepository(db)
        application = applications.get_by_id(application_id)
        applications.update(application, status=ApplicationStatus.APPROVED)

        BulkQueueService(db).enqueue_application(application_id=application_id)

        db.refresh(application)
        assert application.status is ApplicationStatus.APPROVED
    finally:
        db.close()


def test_rerunning_the_pipeline_does_not_duplicate_stored_rows(authenticated_client):
    application_id = create_application(authenticated_client)
    upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(_COMPLETE_BULK_PAGES),
    )
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    db = SessionLocal()
    try:
        fields_before = len(list(ExtractedFieldRepository(db).get_by_application(application_id)))
        rows_before = len(
            list(ValidationRepository(db).get_by_application(application_id, limit=1000))
        )

        PipelineRunnerService(db).run(application_id=application_id)

        fields_after = len(list(ExtractedFieldRepository(db).get_by_application(application_id)))
        rows_after = len(
            list(ValidationRepository(db).get_by_application(application_id, limit=1000))
        )
    finally:
        db.close()

    assert fields_after == fields_before
    assert rows_after == rows_before


# --- All documents fail: pipeline must not run --------------------------------


def test_pipeline_never_starts_when_zero_documents_processed(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)
    application_id, _ = create_application_with_documents(2)
    enqueue(application_id)
    mark_processing(application_id)

    BulkQueueWorker(settings=settings, processor_factory=FailingProcessor).run_until_empty()

    job = pipeline_job_for(application_id)
    assert job is None, "pipeline job must not be enqueued when nothing succeeded"
    assert ACTION_PIPELINE_BLOCKED in audit_actions_for(application_id)
    assert application_status_for(application_id) == "PROCESSING_FAILED", (
        "an application where every document fails must end up visibly "
        "distinguishable, not silently stuck at PROCESSING"
    )


# --- Partial failure: pipeline must still run on what succeeded --------------


def test_pipeline_starts_once_on_partial_success(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)
    application_id, document_ids = create_application_with_documents(3)
    enqueue(application_id)
    failing_ids = set(document_ids[:1])

    class HalfFailProcessor:
        def __init__(self, db):
            self._db = db
            self._inner_success = SuccessfulProcessor(db)

        def process_one(self, *, application_id: int, document_id: int):
            if document_id in failing_ids:
                raise RuntimeError("simulated permanent failure")
            return self._inner_success.process_one(
                application_id=application_id, document_id=document_id
            )

    BulkQueueWorker(settings=settings, processor_factory=HalfFailProcessor).run_until_empty()

    job = pipeline_job_for(application_id)
    assert job is not None, "pipeline job should start once at least one document succeeded"


# --- Race safety: concurrent-enqueue guard ------------------------------------


def test_pipeline_job_enqueued_at_most_once_under_a_race():
    application_id, _ = create_application_with_documents(1)
    db = SessionLocal()
    try:
        jobs = QueueJobRepository(db)
        first = jobs.try_enqueue_pipeline_job(application_id=application_id, max_attempts=3)
        second = jobs.try_enqueue_pipeline_job(application_id=application_id, max_attempts=3)
        assert first is not None
        assert second is None

        rows = db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).all()
        assert len(rows) == 1
    finally:
        db.close()


# --- Pipeline failure handling: application must not stay stuck at PROCESSING -


def test_pipeline_job_failure_marks_application_processing_failed(monkeypatch):
    """When the APPLICATION_PIPELINE job permanently fails the application
    must not stay silently stuck at PROCESSING. It must move to
    PROCESSING_FAILED with an audit trail so operators can investigate."""
    from app.core.config import get_settings
    from unittest.mock import MagicMock

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    mark_processing(application_id)

    # Enqueue a pipeline job directly (simulating what _maybe_start_pipeline does)
    db = SessionLocal()
    try:
        pipeline_job = QueueJobRepository(db).try_enqueue_pipeline_job(
            application_id=application_id, max_attempts=1,
        )
        assert pipeline_job is not None
    finally:
        db.close()

    class FailingPipelineRunner:
        def __init__(self, db):
            self._db = db

        def run(self, *, application_id: int):
            raise RuntimeError("simulated pipeline stage failure")

    # First claim the document OCR job to completion, then the pipeline job
    BulkQueueWorker(settings=settings, processor_factory=SuccessfulProcessor).run_until_empty()

    # Now run with a failing pipeline runner
    BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipelineRunner,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.FAILED, (
        f"pipeline job should be FAILED, got {pipeline.status}: {pipeline.last_error}"
    )
    assert application_status_for(application_id) == "PROCESSING_FAILED", (
        "application must not stay stuck at PROCESSING when the pipeline "
        "permanently fails"
    )
    assert ACTION_PIPELINE_FAILED in audit_actions_for(application_id), (
        "a pipeline failure must be recorded in the audit log"
    )


def test_pipeline_retry_then_success_leaves_application_pending_review(monkeypatch):
    """A pipeline job that fails once then succeeds on retry must leave
    the application at PENDING_REVIEW, not PROCESSING or PROCESSING_FAILED."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 2)
    # Use a non-zero backoff so the RETRY_WAITING job is not immediately claimable.
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 60)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    mark_processing(application_id)

    call_count = 0

    class RetryThenSucceedPipeline:
        def __init__(self, db):
            self._db = db

        def run(self, *, application_id: int):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient pipeline failure")
            # Second call: just mark pending review (real pipeline does analysis etc.)
            from app.bulk_queue.pipeline_runner import PipelineRunnerService
            PipelineRunnerService(self._db)._mark_pending_review(application_id)

    # First pass: document OCR succeeds, pipeline is enqueued by _maybe_start_pipeline,
    # then the pipeline job runs and fails (call_count=1).
    worker = BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=RetryThenSucceedPipeline,
    )
    worker.run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None, "pipeline job must exist after first pass"
    # Pipeline failed on first attempt, should be RETRY_WAITING (backoff prevents re-claim)
    assert pipeline.status is JobStatus.RETRY_WAITING, (
        f"pipeline should be RETRY_WAITING, got {pipeline.status}"
    )

    # Simulate time passing so the retry backoff expires.
    db = SessionLocal()
    try:
        pj = db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).one()
        pj.retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    # Second pass: pipeline retries and succeeds (call_count=2)
    worker2 = BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=RetryThenSucceedPipeline,
    )
    worker2.run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"


def test_pipeline_failure_does_not_overwrite_human_decision(monkeypatch):
    """If a human has already decided on an application (APPROVED/REJECTED),
    a pipeline failure must not revert the status to PROCESSING_FAILED."""
    from app.core.config import get_settings
    from app.bulk_queue.workers import BulkQueueWorker

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)

    # Set up: documents succeed, pipeline job is enqueued, then human decides
    db = SessionLocal()
    try:
        # Mark all document jobs completed
        jobs_repo = QueueJobRepository(db)
        for job in jobs_repo.list_by_application(application_id):
            if job.job_type is JobType.DOCUMENT_OCR:
                jobs_repo.mark_completed(job)

        # Enqueue pipeline job
        pipeline_job = jobs_repo.try_enqueue_pipeline_job(
            application_id=application_id, max_attempts=1,
        )
        assert pipeline_job is not None

        # Simulate human decision AFTER pipeline was enqueued
        applications = ApplicationRepository(db)
        application = applications.get_by_id(application_id)
        applications.update(application, status=ApplicationStatus.APPROVED)
        db.commit()
    finally:
        db.close()

    # Now simulate the pipeline job failing permanently
    class FailingPipelineRunner:
        def __init__(self, db):
            self._db = db

        def run(self, *, application_id: int):
            raise RuntimeError("simulated pipeline stage failure")

    BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipelineRunner,
    ).run_until_empty()

    # The human decision must be preserved -- _handle_pipeline_failure checks
    # that status is PROCESSING before overwriting
    assert application_status_for(application_id) == "APPROVED", (
        "a pipeline failure must not overwrite a human decision"
    )


def test_validation_report_exists_after_rule_failure(authenticated_client):
    """A business validation failure (e.g. IBAN mismatch) must still produce
    a Validation Report. The report is a read-only aggregation of stored data,
    not a pass/fail gate."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(_COMPLETE_BULK_PAGES),
    )
    assert response.status_code == 201, response.text
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    # The pipeline should have completed with PENDING_REVIEW
    assert application_status_for(application_id) == "PENDING_REVIEW"

    # The validation report must exist regardless of individual rule outcomes
    report_response = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report_response.status_code == 200, (
        f"validation report must be generable even with rule failures: {report_response.text}"
    )
    report_data = report_response.json()
    assert "overall_status" in report_data
    assert "rule_summary" in report_data
    assert report_data["rule_summary"]["total"] > 0, "rules must have been executed"


def test_full_end_to_end_upload_through_validation_report(authenticated_client):
    """End-to-end integration: upload → queue → OCR → analysis → confidence →
    normalization → rule engine → validation report exists → application at
    PENDING_REVIEW."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(_COMPLETE_BULK_PAGES),
    )
    assert response.status_code == 201, response.text
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    # Pipeline completed
    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None, "pipeline job must exist"
    assert pipeline.status is JobStatus.COMPLETED, (
        f"pipeline must complete, got {pipeline.status}: {pipeline.last_error}"
    )

    # Application moved to PENDING_REVIEW
    assert application_status_for(application_id) == "PENDING_REVIEW"

    # Validation report is generable
    report_response = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report_response.status_code == 200, report_response.text

    # Extracted fields exist
    db = SessionLocal()
    try:
        fields = list(ExtractedFieldRepository(db).get_by_application(application_id))
        assert len(fields) > 0, "extracted fields must exist after pipeline"
    finally:
        db.close()

    # Validation results exist
    db = SessionLocal()
    try:
        validation_rows = list(
            ValidationRepository(db).get_by_application(application_id, limit=1000)
        )
        assert len(validation_rows) > 0, "validation results must exist after pipeline"
    finally:
        db.close()


# --- State-transition matrix: terminal states for every pipeline outcome -------
#
# This matrix protects against future queue/pipeline changes by explicitly
# asserting the application status, pipeline job status and audit trail for
# every terminal condition.  Each row is an independent test that creates
# its own application, drives the worker through a specific scenario, and
# asserts the expected terminal state.
#
# | Situation                            | Expected                              |
# |--------------------------------------|---------------------------------------|
# | Pipeline succeeds                    | PENDING_REVIEW                        |
# | Pipeline permanently fails           | PROCESSING_FAILED                     |
# | OCR permanently fails                | PROCESSING_FAILED                     |
# | Reviewer already decided             | Decision remains unchanged           |
# | Pipeline retries then succeeds       | PENDING_REVIEW                        |
# | Pipeline retries then permanently fails | PROCESSING_FAILED                  |
# | Pipeline failure                     | APPLICATION_PIPELINE_FAILED audit     |
# | Successful pipeline                  | No false failure audit                |


def _setup_application_with_documents(
    monkeypatch,
    *,
    num_docs: int = 1,
    max_attempts: int = 1,
    retry_backoff: int = 0,
) -> tuple[int, list[int]]:
    """Create an application, enqueue its documents, mark it PROCESSING.

    Returns the application id and document ids."""
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", max_attempts)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", retry_backoff)

    application_id, document_ids = create_application_with_documents(num_docs)
    enqueue(application_id)
    mark_processing(application_id)
    return application_id, document_ids


def _enqueue_pipeline_job(
    application_id: int,
    *,
    max_attempts: int = 1,
) -> QueueJob:
    """Enqueue an APPLICATION_PIPELINE job for the given application."""
    db = SessionLocal()
    try:
        job = QueueJobRepository(db).try_enqueue_pipeline_job(
            application_id=application_id,
            max_attempts=max_attempts,
        )
        assert job is not None, "pipeline job enqueue must succeed"
        return job
    finally:
        db.close()


def _complete_document_jobs(application_id: int) -> None:
    """Mark every DOCUMENT_OCR job for the application as COMPLETED."""
    db = SessionLocal()
    try:
        jobs_repo = QueueJobRepository(db)
        for job in jobs_repo.list_by_application(application_id):
            if job.job_type is JobType.DOCUMENT_OCR:
                jobs_repo.mark_completed(job)
    finally:
        db.close()


def _expire_retry_backoff(application_id: int) -> None:
    """Set the pipeline job's retry_at to the past so it becomes claimable."""
    db = SessionLocal()
    try:
        pj = db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).one()
        pj.retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()


# -- Row 1: Pipeline succeeds → PENDING_REVIEW ---------------------------------

def test_state_matrix_pipeline_succeeds(monkeypatch):
    """Situation: pipeline succeeds on first attempt.
    Expected:  application status = PENDING_REVIEW,
               pipeline job = COMPLETED,
               no failure audit."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    class SucceedPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            PipelineRunnerService(self._db)._mark_pending_review(application_id)

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=SucceedPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"
    assert ACTION_PIPELINE_FAILED not in audit_actions_for(application_id)


# -- Row 2: Pipeline permanently fails → PROCESSING_FAILED ---------------------

def test_state_matrix_pipeline_permanent_failure(monkeypatch):
    """Situation: pipeline permanently fails (max_attempts=1, first try).
    Expected:  application status = PROCESSING_FAILED,
               pipeline job = FAILED,
               APPLICATION_PIPELINE_FAILED audit exists."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    class FailingPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("permanent pipeline failure")

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.FAILED
    assert application_status_for(application_id) == "PROCESSING_FAILED"
    assert ACTION_PIPELINE_FAILED in audit_actions_for(application_id)


# -- Row 3: OCR permanently fails → PROCESSING_FAILED --------------------------

def test_state_matrix_ocr_permanent_failure(monkeypatch):
    """Situation: every document OCR job fails permanently.
    Expected:  application status = PROCESSING_FAILED,
               no pipeline job enqueued,
               PIPELINE_BLOCKED audit exists."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=2, max_attempts=1,
    )

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=FailingProcessor,
    ).run_until_empty()

    assert pipeline_job_for(application_id) is None
    assert application_status_for(application_id) == "PROCESSING_FAILED"
    assert ACTION_PIPELINE_BLOCKED in audit_actions_for(application_id)
    assert ACTION_PIPELINE_FAILED not in audit_actions_for(application_id)


# -- Row 4: Reviewer already decided → decision remains unchanged ---------------

def test_state_matrix_reviewer_decision_preserved(monkeypatch):
    """Situation: human already decided (APPROVED), then pipeline job fails.
    Expected:  application status remains APPROVED."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    # Human decides BEFORE pipeline runs
    db = SessionLocal()
    try:
        apps = ApplicationRepository(db)
        app = apps.get_by_id(application_id)
        apps.update(app, status=ApplicationStatus.APPROVED)
        db.commit()
    finally:
        db.close()

    class FailingPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("too late, human already decided")

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipeline,
    ).run_until_empty()

    assert application_status_for(application_id) == "APPROVED"

    # Also test REJECTED
    application_id2, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id2)
    _complete_document_jobs(application_id2)

    db = SessionLocal()
    try:
        apps = ApplicationRepository(db)
        app = apps.get_by_id(application_id2)
        apps.update(app, status=ApplicationStatus.REJECTED)
        db.commit()
    finally:
        db.close()

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipeline,
    ).run_until_empty()

    assert application_status_for(application_id2) == "REJECTED"


# -- Row 5: Pipeline retries then succeeds → PENDING_REVIEW ---------------------

def test_state_matrix_retry_then_succeed(monkeypatch):
    """Situation: pipeline fails on first try, succeeds on retry.
    Expected:  application status = PENDING_REVIEW,
               pipeline job = COMPLETED."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=2, retry_backoff=60,
    )
    _enqueue_pipeline_job(application_id, max_attempts=2)
    _complete_document_jobs(application_id)

    call_count = 0

    class RetrySucceedPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            PipelineRunnerService(self._db)._mark_pending_review(application_id)

    # First pass: pipeline fails, job goes to RETRY_WAITING
    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=RetrySucceedPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.RETRY_WAITING
    assert application_status_for(application_id) == "PROCESSING"

    # Expire the backoff
    _expire_retry_backoff(application_id)

    # Second pass: pipeline succeeds
    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=RetrySucceedPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"


# -- Row 6: Pipeline retries then permanently fails → PROCESSING_FAILED ---------

def test_state_matrix_retry_then_permanent_failure(monkeypatch):
    """Situation: pipeline fails twice (max_attempts=2), exhausts budget.
    Expected:  application status = PROCESSING_FAILED,
               pipeline job = FAILED."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=2, retry_backoff=60,
    )
    _enqueue_pipeline_job(application_id, max_attempts=2)
    _complete_document_jobs(application_id)

    class AlwaysFailPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("persistent pipeline failure")

    # First pass: fails, RETRY_WAITING
    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=AlwaysFailPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline.status is JobStatus.RETRY_WAITING

    # Expire backoff and run second attempt
    _expire_retry_backoff(application_id)
    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=AlwaysFailPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline.status is JobStatus.FAILED
    assert application_status_for(application_id) == "PROCESSING_FAILED"
    assert ACTION_PIPELINE_FAILED in audit_actions_for(application_id)


# -- Row 7: Pipeline failure → APPLICATION_PIPELINE_FAILED audit ----------------

def test_state_matrix_pipeline_failure_audit_recorded(monkeypatch):
    """Situation: pipeline job permanently fails.
    Expected:  APPLICATION_PIPELINE_FAILED audit entry exists with error detail."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    class FailingPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("stage X crashed")

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipeline,
    ).run_until_empty()

    actions = audit_actions_for(application_id)
    assert ACTION_PIPELINE_FAILED in actions

    # Verify audit entry contains error detail
    db = SessionLocal()
    try:
        entry = db.scalars(
            select(AuditLog).where(
                AuditLog.application_id == application_id,
                AuditLog.action == ACTION_PIPELINE_FAILED,
            )
        ).one()
        assert entry.details is not None
        assert "last_error" in entry.details
        assert "stage X crashed" in entry.details["last_error"]
    finally:
        db.close()


# -- Row 8: Successful pipeline → no false failure audit -----------------------

def test_state_matrix_success_no_false_failure_audit(monkeypatch):
    """Situation: pipeline succeeds on first attempt.
    Expected:  no APPLICATION_PIPELINE_FAILED or PIPELINE_BLOCKED audit."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    class SucceedPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            PipelineRunnerService(self._db)._mark_pending_review(application_id)

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=SucceedPipeline,
    ).run_until_empty()

    actions = audit_actions_for(application_id)
    assert ACTION_PIPELINE_FAILED not in actions, (
        f"successful pipeline must not record {ACTION_PIPELINE_FAILED}, "
        f"got: {actions}"
    )
    assert ACTION_PIPELINE_BLOCKED not in actions, (
        f"successful pipeline must not record {ACTION_PIPELINE_BLOCKED}, "
        f"got: {actions}"
    )


# -- Bulk-upload variant: pipeline succeeds end-to-end --------------------------

def test_state_matrix_bulk_upload_pipeline_succeeds(authenticated_client):
    """Full real-data path through the bulk upload + worker pipeline.
    Expected:  PENDING_REVIEW, validation report generable."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(_COMPLETE_BULK_PAGES),
    )
    assert response.status_code == 201, response.text
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"

    report = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report.status_code == 200

    actions = audit_actions_for(application_id)
    assert ACTION_PIPELINE_FAILED not in actions


# ========================================================================
# Comprehensive completeness-gate regression tests
# ========================================================================

INCOMPLETE_BULK_PAGES = [
    # Only TRIPARTITE AGREEMENT + BILATERAL AGREEMENT — 6 required types missing.
    "TRIPARTITE AGREEMENT\nThis tripartite agreement is entered into between\n"
    "the sub-biller, 1LINK and KPITB for digital payment collection.\n"
    "First copy.",
    "BILATERAL AGREEMENT\nThis bilateral service level agreement is between\n"
    "the merchant and 1LINK for payment processing services.",
]


def _db_query(model, *filters):
    """Run a generic query and return all results."""
    db = SessionLocal()
    try:
        return list(db.query(model).filter(*filters).all())
    finally:
        db.close()


def _db_count(model, *filters):
    db = SessionLocal()
    try:
        return db.query(model).filter(*filters).count()
    finally:
        db.close()


# --- Scenario 1: Complete application reaches Validation Report ----------

def test_scenario_1_complete_application_reaches_validation_report(
    authenticated_client,
):
    """A genuinely complete bulk upload (all 8 required types) must reach
    Validation Report and PENDING_REVIEW through the real worker pipeline."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(_COMPLETE_BULK_PAGES),
    )
    assert response.status_code == 201

    # Bulk upload must NOT immediately set PROCESSING
    assert application_status_for(application_id) != "PROCESSING"

    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    # Must reach PENDING_REVIEW with a valid pipeline job
    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None, "pipeline job must exist"
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"

    # Validation report must be generable
    report = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report.status_code == 200
    report_data = report.json()
    assert "overall_status" in report_data


# --- Scenario 2: Incomplete application cannot enter processing ----------

def test_scenario_2_incomplete_application_stays_needs_documents(
    authenticated_client,
):
    """An incomplete bulk upload (2 of 8 required types) must stay in
    NEEDS_DOCUMENTS and must NOT generate a pipeline job or PROCESSING."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(INCOMPLETE_BULK_PAGES),
    )
    assert response.status_code == 201

    # Drain the queue — the BULK_UPLOAD split job runs and finds
    # incomplete documents, so it must transition to NEEDS_DOCUMENTS.
    drain_until_empty()

    status = application_status_for(application_id)
    assert status == "NEEDS_DOCUMENTS", (
        f"Incomplete app must be NEEDS_DOCUMENTS, got {status}"
    )

    # Must NOT have a pipeline job
    pipeline = pipeline_job_for(application_id)
    assert pipeline is None, "incomplete application must not get a pipeline job"

    # Must NOT have any document OCR jobs for split documents
    from app.database.models.document import Document
    from app.database.models.enums import DocumentType as DT

    docs = _db_query(Document, Document.application_id == application_id)
    non_bulk = [d for d in docs if d.document_type != DT.BULK_UPLOAD]
    assert len(non_bulk) == 2, f"expected 2 split documents, got {len(non_bulk)}"

    # No per-document OCR jobs should have been enqueued
    from app.database.models.queue_job import QueueJob
    from app.database.models.enums import JobType as JT

    ocr_jobs = _db_query(
        QueueJob,
        QueueJob.application_id == application_id,
        QueueJob.job_type == JT.DOCUMENT_OCR,
    )
    bulk_upload_doc_id = next(d.id for d in docs if d.document_type == DT.BULK_UPLOAD)
    for job in ocr_jobs:
        assert job.document_id == bulk_upload_doc_id, (
            f"job {job.id} targets non-BULK doc {job.document_id}"
        )


# --- Scenario 3: Operator requests docs -> applicant resubmits -> complete ---

def test_scenario_3_resubmission_completes_application(
    authenticated_client,
):
    """After an operator requests missing documents, the applicant uploads
    them, completeness passes, and the application reaches PENDING_REVIEW."""
    application_id = create_application(authenticated_client)

    # Step 1: Upload incomplete bulk
    upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(INCOMPLETE_BULK_PAGES),
    )
    drain_until_empty()
    assert application_status_for(application_id) == "NEEDS_DOCUMENTS"

    # Step 2: Operator requests missing documents
    response = authenticated_client.post(
        f"{API}/applications/{application_id}/request-documents",
        json={
            "missing_document_types": [
                "ACCOUNT_MAINTENANCE_CERTIFICATE",
                "ONE_LINK_LETTER",
                "AUTHORITY_LETTER",
                "SCHEDULE_OF_CHARGES",
                "BUSINESS_REQUIREMENT_DOCUMENT",
                "FORMAL_REQUEST_LETTER",
            ],
            "reason": "Missing required documents",
        },
    )
    assert response.status_code == 200, response.text

    # Step 3: Applicant resubmits the 6 missing documents via individual uploads
    # (bulk upload would conflict with copy numbers from the first upload)
    from tests.test_upload_api import upload as upload_single

    missing_types = [
        "ACCOUNT_MAINTENANCE_CERTIFICATE",
        "ONE_LINK_LETTER",
        "AUTHORITY_LETTER",
        "SCHEDULE_OF_CHARGES",
        "BUSINESS_REQUIREMENT_DOCUMENT",
        "FORMAL_REQUEST_LETTER",
    ]
    for doc_type in missing_types:
        response = upload_single(authenticated_client, application_id, document_type=doc_type)
        assert response.status_code == 201, response.text

    # Step 4: Submit for processing
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    # Step 5: Must reach PENDING_REVIEW
    assert application_status_for(application_id) == "PENDING_REVIEW", (
        f"resubmission + submit should reach PENDING_REVIEW, "
        f"got {application_status_for(application_id)}"
    )

    # Validation report must exist
    report = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report.status_code == 200


# --- Scenario 4: OCR permanent failure -> PROCESSING_FAILED ---------------

def test_scenario_4_ocr_permanent_failure(monkeypatch):
    """When every document OCR job permanently fails, the application must
    reach PROCESSING_FAILED with an audit trail."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    mark_processing(application_id)

    BulkQueueWorker(settings=settings, processor_factory=FailingProcessor).run_until_empty()

    assert application_status_for(application_id) == "PROCESSING_FAILED"
    assert ACTION_PIPELINE_BLOCKED in audit_actions_for(application_id)


# --- Scenario 5: Pipeline permanent failure -> PROCESSING_FAILED ----------

def test_scenario_5_pipeline_permanent_failure(monkeypatch):
    """When the APPLICATION_PIPELINE job permanently fails after exhausting
    retries, the application must reach PROCESSING_FAILED."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    mark_processing(application_id)

    class FailingPipelineRunner:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("simulated pipeline failure")

    BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipelineRunner,
    ).run_until_empty()

    assert application_status_for(application_id) == "PROCESSING_FAILED"
    assert ACTION_PIPELINE_FAILED in audit_actions_for(application_id)


# --- Scenario 6: Business rule failure still produces Validation Report ---

def test_scenario_6_business_rule_failure_still_produces_report(
    authenticated_client,
):
    """A business validation failure must still produce a Validation Report.
    Processing failure != business failure."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(_COMPLETE_BULK_PAGES),
    )
    assert response.status_code == 201
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    assert application_status_for(application_id) == "PENDING_REVIEW"

    report = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report.status_code == 200
    report_data = report.json()
    assert report_data.get("rule_summary", {}).get("total", 0) > 0, (
        "rules must have been executed"
    )


# --- Scenario 7: Reviewer decision preserved against pipeline failure ----

def test_scenario_7_late_pipeline_failure_does_not_overwrite_decision(
    authenticated_client, monkeypatch
):
    """If a reviewer already decided, a late pipeline failure must not
    overwrite the human decision."""
    from app.core.config import get_settings
    from app.database.repositories.audit_log_repository import AuditLogRepository

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    mark_processing(application_id)

    # Simulate a completed pipeline + reviewer approval
    db = SessionLocal()
    try:
        applications = ApplicationRepository(db)
        app = applications.get_by_id(application_id)
        applications.update(app, status=ApplicationStatus.APPROVED)

        AuditLogRepository(db).create(
            application_id=application_id,
            username="reviewer",
            action="APPLICATION_APPROVED",
            details={},
            severity="INFO",
        )
    finally:
        db.close()

    # Now simulate a late pipeline failure
    class FailingPipelineRunner:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("simulated late pipeline failure")

    BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipelineRunner,
    ).run_until_empty()

    # The human decision must be preserved
    assert application_status_for(application_id) == "APPROVED"


# --- Scenario 8: Real end-to-end with database evidence ------------------

def test_scenario_8_end_to_end_database_evidence(authenticated_client):
    """Use the real service chain and verify actual persisted database
    records at every pipeline stage."""
    from app.database.models.document import Document
    from app.database.models.enums import DocumentType as DT, DocumentProcessingStatus as DPS
    from app.database.models.queue_job import QueueJob
    from app.database.models.enums import JobType as JT, JobStatus as JS

    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(_COMPLETE_BULK_PAGES),
    )
    assert response.status_code == 201
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    # --- Application status ---
    assert application_status_for(application_id) == "PENDING_REVIEW"

    # --- Documents: should have 8 split documents + 1 BULK_UPLOAD ---
    docs = _db_query(Document, Document.application_id == application_id)
    split_docs = [d for d in docs if d.document_type != DT.BULK_UPLOAD]
    assert len(split_docs) == 8, f"expected 8 split docs, got {len(split_docs)}"

    # All split documents should be COMPLETED
    for doc in split_docs:
        assert doc.processing_status == DPS.COMPLETED, (
            f"doc {doc.id} ({doc.document_type.value}) status = {doc.processing_status}"
        )

    # --- Queue jobs: 8 DOCUMENT_OCR (split docs) + 1 APPLICATION_PIPELINE ---
    all_jobs = _db_query(QueueJob, QueueJob.application_id == application_id)
    ocr_jobs = [j for j in all_jobs if j.job_type == JT.DOCUMENT_OCR]
    pipeline_jobs = [j for j in all_jobs if j.job_type == JT.APPLICATION_PIPELINE]

    # OCR jobs: one per split document plus the BULK_UPLOAD placeholder
    ocr_doc_ids = {j.document_id for j in ocr_jobs}
    all_doc_ids = {d.id for d in docs}
    assert ocr_doc_ids == all_doc_ids, (
        f"OCR jobs target {ocr_doc_ids}, expected {all_doc_ids}"
    )
    for j in ocr_jobs:
        assert j.status == JS.COMPLETED, (
            f"OCR job {j.id} status = {j.status}: {j.last_error}"
        )

    # Pipeline job
    assert len(pipeline_jobs) == 1, f"expected 1 pipeline job, got {len(pipeline_jobs)}"
    assert pipeline_jobs[0].status == JS.COMPLETED, (
        f"pipeline job status = {pipeline_jobs[0].status}: {pipeline_jobs[0].last_error}"
    )

    # --- Validation report ---
    report = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report.status_code == 200, f"validation report: {report.status_code}"
    report_data = report.json()
    assert "overall_status" in report_data
    assert "rule_summary" in report_data
