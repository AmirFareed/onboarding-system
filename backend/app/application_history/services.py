"""Business service for the Application History API.

Reads the existing application lifecycle tables (applications, documents,
application_validation_history, queue_jobs, human_reviews) and presents them
as a chronological, human-readable timeline. This module never writes anything
and never invents events: it only projects what the rest of the system already
recorded, in the vocabulary the other modules use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application_history.schemas import (
    ApplicationHistoryListItem,
    TimelineEvent,
)
from app.database.models.document import Document
from app.database.models.enums import (
    ApplicationStatus,
    JobStatus,
    JobType,
    ReviewDecision,
    ValidationEventType,
)
from app.database.models.human_review import HumanReview
from app.database.models.queue_job import QueueJob
from app.database.models.validation_history import ValidationHistoryEntry
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.human_review_repository import HumanReviewRepository
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.database.repositories.validation_history_repository import (
    ValidationHistoryRepository,
)


class ApplicationNotFoundError(Exception):
    """Raised when an application id does not exist."""


@dataclass
class _RawEvent:
    """Internal, presorted timeline event before schema serialization."""

    timestamp: datetime
    kind: str
    label: str
    actor_name: str | None = None
    actor_role: str | None = None
    detail: str | None = None
    document_type: str | None = None
    copy_number: int | None = None
    filename: str | None = None


def _event_kind_for_history(event_type: ValidationEventType) -> str:
    """Map a validation-history event to a stable timeline kind.

    The REVIEW_* history event types exist in the enum but are never written
    (human_verification records decisions on ``human_reviews``, not history);
    they are still mapped so any future writer renders consistently.
    """
    mapping = {
        ValidationEventType.DOCUMENTS_REQUESTED: "DOCUMENTS_REQUESTED",
        ValidationEventType.DOCUMENTS_RECEIVED: "DOCUMENTS_RECEIVED",
        ValidationEventType.OPERATOR_SUBMITTED: "OPERATOR_SUBMITTED",
        ValidationEventType.OPERATOR_REJECTED: "OPERATOR_REJECTED",
        ValidationEventType.SUBMITTED_FOR_PROCESSING: "SUBMITTED_FOR_PROCESSING",
        ValidationEventType.PROCESSING_FAILED: "PROCESSING_FAILED",
        ValidationEventType.REVIEW_APPROVED: "REVIEW_DECISION",
        ValidationEventType.REVIEW_CORRECTED: "REVIEW_DECISION",
        ValidationEventType.REVIEW_REJECTED: "REVIEW_DECISION",
    }
    return mapping.get(event_type, "WORKFLOW")


def _history_label(
    event_type: ValidationEventType, reason: str | None, missing: list[str] | None
) -> str:
    """Build the human-readable summary for a history event."""
    if event_type is ValidationEventType.DOCUMENTS_REQUESTED:
        return "Missing documents requested from applicant"
    if event_type is ValidationEventType.DOCUMENTS_RECEIVED:
        return "Documents received"
    if event_type is ValidationEventType.OPERATOR_SUBMITTED:
        return "Application submitted by operator"
    if event_type is ValidationEventType.OPERATOR_REJECTED:
        return "Application rejected by operator"
    if event_type is ValidationEventType.SUBMITTED_FOR_PROCESSING:
        return "Submitted for processing"
    if event_type is ValidationEventType.PROCESSING_FAILED:
        return "Processing failed"
    if event_type is ValidationEventType.REVIEW_APPROVED:
        return "Application approved"
    if event_type is ValidationEventType.REVIEW_CORRECTED:
        return "Application corrected"
    if event_type is ValidationEventType.REVIEW_REJECTED:
        return "Application rejected by reviewer"
    return "Workflow update"


def _history_detail(
    event_type: ValidationEventType, reason: str | None, missing: list[str] | None
) -> str | None:
    """Build the evidence detail line for a history event."""
    if event_type is ValidationEventType.DOCUMENTS_REQUESTED:
        parts: list[str] = []
        if missing:
            parts.append("Requested: " + ", ".join(missing))
        if reason:
            parts.append(reason)
        return " — ".join(parts) if parts else None
    if reason:
        return reason
    return None


def _history_events(entries: list[ValidationHistoryEntry]) -> list[_RawEvent]:
    """Convert validation-history entries into raw timeline events."""
    return [
        _RawEvent(
            timestamp=entry.created_at,
            kind=_event_kind_for_history(entry.event_type),
            label=_history_label(
                entry.event_type, entry.reason, entry.missing_document_types
            ),
            actor_name=entry.actor_name,
            actor_role=entry.actor_role,
            detail=_history_detail(
                entry.event_type, entry.reason, entry.missing_document_types
            ),
        )
        for entry in entries
    ]


def _document_events(documents: list[Document]) -> list[_RawEvent]:
    """Convert document rows into upload timeline events.
    
    Provides structured metadata (document_type, copy_number, filename) so the
    frontend does not need to parse enum values from the label string.
    """
    events: list[_RawEvent] = []
    for doc in documents:
        events.append(
            _RawEvent(
                timestamp=doc.uploaded_at,
                kind="DOCUMENT_UPLOADED",
                label="Document uploaded",
                document_type=doc.document_type.value,
                copy_number=doc.copy_number,
                filename=doc.original_filename,
            )
        )
    return events


def _review_events(reviews: list[HumanReview]) -> list[_RawEvent]:
    """Convert human-review decisions into timeline events."""
    labels = {
        ReviewDecision.APPROVE: "Application approved",
        ReviewDecision.CORRECT: "Application corrected",
        ReviewDecision.REJECT: "Application rejected by reviewer",
    }
    events: list[_RawEvent] = []
    for review in reviews:
        comment = review.comments or review.rejection_reason
        events.append(
            _RawEvent(
                timestamp=review.reviewed_at,
                kind="REVIEW_DECISION",
                label=labels.get(review.decision, "Review decision"),
                actor_name=review.reviewer_name,
                detail=comment,
            )
        )
    return events


def _processing_events(jobs: list[QueueJob]) -> list[_RawEvent]:
    """Convert pipeline completion into a single timeline event.

    Only the application-level pipeline job marks the end of processing (it is
    what transitions the application to PENDING_REVIEW); individual document
    OCR jobs are per-document internals and are deliberately not shown.
    """
    events: list[_RawEvent] = []
    for job in jobs:
        if job.job_type is not JobType.APPLICATION_PIPELINE:
            continue
        if job.completed_at is not None:
            label = "Processing completed"
            detail = None
            if job.status is JobStatus.FAILED:
                label = "Processing failed"
                detail = job.last_error
            events.append(
                _RawEvent(
                    timestamp=job.completed_at,
                    kind="PROCESSING_COMPLETED",
                    label=label,
                    detail=detail,
                )
            )
    return events


def _find_latest(entries: list[ValidationHistoryEntry]) -> ValidationHistoryEntry | None:
    """Return the newest history entry from a (newest-first) list."""
    return entries[0] if entries else None


class ApplicationHistoryService:
    """Read-only projection of application lifecycle data for IT."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._history = ValidationHistoryRepository(db)
        self._reviews = HumanReviewRepository(db)
        self._jobs = QueueJobRepository(db)

    def list_applications(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        query: str | None = None,
        status: ApplicationStatus | None = None,
    ) -> tuple[list[ApplicationHistoryListItem], int]:
        """Return the paginated application history list.

        Each row carries the application's metadata plus the most recent
        workflow event across validation history, document uploads and review
        decisions (whichever happened last), so the list reads as "what
        happened last" per application.
        """
        applications, total = self._applications.search(
            offset=offset, limit=limit, query=query, status=status
        )
        if not applications:
            return [], total

        ids = [app.id for app in applications]

        # Fetch the candidate "latest event" sources in bulk (three queries,
        # not N+1) then pick the newest per application in Python.
        history_rows = self._db.scalars(
            select(ValidationHistoryEntry)
            .where(ValidationHistoryEntry.application_id.in_(ids))
            .order_by(
                ValidationHistoryEntry.created_at.desc(),
                ValidationHistoryEntry.id.desc(),
            )
        ).all()
        review_rows = self._db.scalars(
            select(HumanReview)
            .where(HumanReview.application_id.in_(ids))
            .order_by(HumanReview.reviewed_at.desc(), HumanReview.id.desc())
        ).all()
        document_rows = self._db.scalars(
            select(Document)
            .where(Document.application_id.in_(ids))
            .order_by(Document.uploaded_at.desc(), Document.id.desc())
        ).all()

        latest_by_app: dict[int, tuple[ValidationEventType | None, datetime]] = {}
        for entry in history_rows:
            latest_by_app.setdefault(entry.application_id, (entry.event_type, entry.created_at))
        for review in review_rows:
            key = "REVIEW_APPROVED"
            if review.decision is ReviewDecision.CORRECT:
                key = "REVIEW_CORRECTED"
            elif review.decision is ReviewDecision.REJECT:
                key = "REVIEW_REJECTED"
            current = latest_by_app.get(review.application_id)
            if current is None or review.reviewed_at > current[1]:
                latest_by_app[review.application_id] = (ValidationEventType(key), review.reviewed_at)
        for doc in document_rows:
            current = latest_by_app.get(doc.application_id)
            if current is None or doc.uploaded_at > current[1]:
                latest_by_app[doc.application_id] = (
                    ValidationEventType.DOCUMENTS_RECEIVED,
                    doc.uploaded_at,
                )

        items = []
        for app in applications:
            last_event_type, last_event_at = latest_by_app.get(app.id, (None, None))
            items.append(
                ApplicationHistoryListItem(
                    application_id=app.id,
                    application_name=app.name,
                    status=app.status,
                    submitted_at=app.submitted_at,
                    updated_at=app.updated_at,
                    created_by=app.created_by,
                    last_event_type=last_event_type,
                    last_event_at=last_event_at,
                )
            )
        return items, total

    def get_timeline(self, application_id: int) -> ApplicationHistoryListItem | None:
        """Return the application (or ``None`` when it does not exist).

        Kept separate from :meth:`timeline` so the route can 404 cleanly.
        """
        return self._applications.get_by_id(application_id)

    def timeline(self, application_id: int) -> list[TimelineEvent]:
        """Assemble the full chronological timeline for an application.

        Merges application creation, document uploads, operator workflow events,
        pipeline completion and review decisions into a single list ordered
        newest last. Every event carries only business-facing fields.
        """
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(f"Application {application_id} not found")

        documents = self._documents.get_all_by_application(application_id)
        history_entries, _ = self._history.list_for_application(
            application_id, limit=1000
        )
        # list_for_application returns newest-first; timeline is oldest-first.
        history_entries = list(reversed(history_entries))
        reviews = list(self._reviews.get_by_application(application_id, limit=1000))
        jobs = self._jobs.list_all_by_application(application_id)

        raw: list[_RawEvent] = [
            _RawEvent(
                timestamp=application.submitted_at,
                kind="APPLICATION_CREATED",
                label="Application created",
                actor_name=application.created_by,
            ),
            *_history_events(history_entries),
            *_document_events(documents),
            *_processing_events(jobs),
            *_review_events(reviews),
        ]

        raw.sort(key=lambda event: event.timestamp)
        return [
            TimelineEvent(
                kind=event.kind,
                label=event.label,
                timestamp=event.timestamp,
                actor_name=event.actor_name,
                actor_role=event.actor_role,
                detail=event.detail,
                document_type=event.document_type,
                copy_number=event.copy_number,
                filename=event.filename,
            )
            for event in raw
        ]