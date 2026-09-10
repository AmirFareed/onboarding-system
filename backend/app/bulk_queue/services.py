"""Service layer for enqueueing and tracking bulk queue jobs."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.bulk_queue.exceptions import ApplicationNotFound
from app.bulk_queue.schemas import (
    CompletenessSummary,
    EnqueueResponse,
    ProcessingActionResponse,
    ProcessingDocumentResponse,
    ProcessingDocumentsResponse,
    ProcessingProgressResponse,
    QueueProgressResponse,
)
from app.completeness.constants import CompletenessStatus
from app.core.config import get_settings
from app.database.models.enums import ApplicationStatus, JobStatus
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.queue_job_repository import QueueJobRepository

logger = logging.getLogger(__name__)


class BulkQueueService:
    """Coordinates application-level queue operations."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._jobs = QueueJobRepository(db)
        self._settings = get_settings()

    def enqueue_application(self, *, application_id: int) -> EnqueueResponse:
        """Enqueue every eligible UPLOADED document for one application."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        completeness = self._completeness_gate(application_id)
        self._validate_uploaded_documents(application_id)
        jobs, created, existing = self._jobs.enqueue_uploaded_documents(
            application_id=application_id,
            max_attempts=self._settings.bulk_queue_max_attempts,
        )
        # Only transition to PROCESSING when the document set is actually
        # complete.  Incomplete applications must remain in their current
        # state (SUBMITTED or NEEDS_DOCUMENTS) so the operator workflow
        # stays unblocked.
        if (
            jobs
            and completeness is not None
            and completeness.status == CompletenessStatus.COMPLETE
        ):
            self._applications.update_status_if(
                application_id,
                new_status=ApplicationStatus.PROCESSING,
                allowed_current_statuses=(
                    ApplicationStatus.SUBMITTED,
                    ApplicationStatus.NEEDS_DOCUMENTS,
                ),
            )
        logger.info(
            "Bulk queue enqueue application_id=%s created=%s existing=%s",
            application_id,
            created,
            existing,
        )
        return EnqueueResponse(
            message="Documents enqueued successfully",
            application_id=application_id,
            jobs_created=created,
            jobs_existing=existing,
            total_jobs=len(jobs),
            jobs=list(jobs),
            completeness=completeness,
        )

    def start_processing(self, *, application_id: int) -> ProcessingActionResponse:
        """Queue all eligible uploaded documents and report the action safely."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        completeness = self._completeness_gate(application_id)
        self._validate_uploaded_documents(application_id)
        jobs, created, _ = self._jobs.enqueue_uploaded_documents(
            application_id=application_id,
            max_attempts=self._settings.bulk_queue_max_attempts,
        )
        # start_processing is called by the operator's explicit action.
        # The completeness check happens later: for bulk uploads the split
        # hasn't happened yet (the placeholder is the only document), so
        # _process_bulk_upload() will re-check after splitting.
        if jobs and application.status in (
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.NEEDS_DOCUMENTS,
        ):
            self._applications.update_status_if(
                application_id,
                new_status=ApplicationStatus.PROCESSING,
                allowed_current_statuses=(
                    ApplicationStatus.SUBMITTED,
                    ApplicationStatus.NEEDS_DOCUMENTS,
                ),
            )
        active = sum(
            1
            for job in jobs
            if job.status in {JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.RETRY_WAITING}
        )
        return ProcessingActionResponse(
            message=("Document processing started" if jobs else "No documents are ready to process"),
            application_id=application_id,
            documents_queued=created,
            documents_already_in_progress=max(active - created, 0),
            completeness=completeness,
        )

    def progress(self, *, application_id: int) -> QueueProgressResponse:
        """Return application queue progress grouped by status."""
        if self._applications.get_by_id(application_id) is None:
            raise ApplicationNotFound()
        counts = self._jobs.progress_for_application(application_id)
        return QueueProgressResponse(
            application_id=application_id,
            total=sum(counts.values()),
            queued=counts.get(JobStatus.QUEUED, 0),
            processing=counts.get(JobStatus.PROCESSING, 0),
            completed=counts.get(JobStatus.COMPLETED, 0),
            failed=counts.get(JobStatus.FAILED, 0),
            retry_waiting=counts.get(JobStatus.RETRY_WAITING, 0),
        )

    def processing_progress(self, *, application_id: int) -> ProcessingProgressResponse:
        """Return business-language progress for one application."""
        if self._applications.get_by_id(application_id) is None:
            raise ApplicationNotFound()
        counts = self._jobs.progress_for_application(application_id)
        total = sum(counts.values())
        completed = counts.get(JobStatus.COMPLETED, 0)
        return ProcessingProgressResponse(
            application_id=application_id,
            total_documents=total,
            queued=counts.get(JobStatus.QUEUED, 0) + counts.get(JobStatus.RETRY_WAITING, 0),
            processing=counts.get(JobStatus.PROCESSING, 0),
            completed=completed,
            failed=counts.get(JobStatus.FAILED, 0),
            progress_percentage=round(completed / total * 100, 1) if total else 0.0,
            documents_needing_attention=counts.get(JobStatus.FAILED, 0),
        )

    def processing_documents(self, *, application_id: int) -> ProcessingDocumentsResponse:
        """Return safe per-document statuses without queue internals."""
        if self._applications.get_by_id(application_id) is None:
            raise ApplicationNotFound()
        documents = []
        for job in self._jobs.list_by_application(application_id):
            status = {
                JobStatus.QUEUED: ("QUEUED", "Waiting to start"),
                JobStatus.RETRY_WAITING: ("QUEUED", "Waiting to retry"),
                JobStatus.PROCESSING: ("PROCESSING", "Processing"),
                JobStatus.COMPLETED: ("COMPLETED", "Processed successfully"),
                JobStatus.FAILED: ("FAILED", "Needs attention"),
            }[job.status]
            documents.append(
                ProcessingDocumentResponse(
                    document_id=job.document_id,
                    file_name=job.document.original_filename if job.document else "Document",
                    status=status[0],
                    message=status[1],
                    updated_at=job.completed_at or job.started_at or job.created_at,
                )
            )
        return ProcessingDocumentsResponse(application_id=application_id, documents=documents)

    def retry_failed(self, *, application_id: int) -> ProcessingActionResponse:
        """Reset failed documents for a deliberate operator retry."""
        if self._applications.get_by_id(application_id) is None:
            raise ApplicationNotFound()
        retried = self._jobs.retry_failed_for_application(application_id)
        return ProcessingActionResponse(
            message=("Failed documents queued for retry" if retried else "No documents need retry"),
            application_id=application_id,
            documents_queued=retried,
            documents_already_in_progress=0,
            documents_retried=retried,
        )

    def _completeness_gate(self, application_id: int) -> CompletenessSummary | None:
        """Run the pre-processing completeness check for an application.

        The pipeline treats completeness as a gate run before expensive
        processing begins: the report is attached to the enqueue/start response
        so the operator immediately sees which required documents are missing.
        The check never blocks processing (documents already uploaded are still
        enqueued); it surfaces the missing-document state so it is visible at
        the moment expensive work starts instead of only at the end of the
        pipeline's rule validation.

        Returns:
            The completeness summary, or ``None`` when the application no
            longer exists.
        """
        from app.completeness.services import CompletenessService

        report = CompletenessService(self._db).verify(application_id=application_id)
        return CompletenessSummary(
            status=report.status.value,
            missing_documents=[
                document_type.value for document_type in report.missing_documents
            ],
            completion_percentage=report.completion_percentage,
        )

    def _validate_uploaded_documents(self, application_id: int) -> None:
        """Run technical validation before any document can be enqueued.

        Both callers above are the only two places that ever enqueue a
        document, so this is the one place that needs the call -- not
        UploadService.upload() itself. Single-upload documents used to be
        enqueued with no stored validation result at all, so
        DocumentProcessingService.process_one()'s PASS-gate skipped them
        forever; this closes that gap the same way it's already closed for
        bulk-split documents (which validate lazily inside process_one after
        splitting -- a different, still-necessary call for a different set of
        documents, not replaced by this one).
        """
        from app.technical_validation.services import TechnicalValidationService

        TechnicalValidationService(self._db).validate(application_id=application_id)
