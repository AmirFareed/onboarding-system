"""Pydantic schemas for the Application History API.

Business-facing only: application metadata plus a chronological, human-readable
timeline of lifecycle events. Never raw JSON, OCR text or extracted PII.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import ApplicationStatus, ValidationEventType


class ApplicationHistoryListItem(BaseModel):
    """One application in the Application History list.

    Fields are the same business-level metadata the rest of the UI already
    surfaces (status, submission/update times, creator) plus the most recent
    workflow event so the list reads as "what happened last" at a glance.
    """

    model_config = ConfigDict(from_attributes=True)

    application_id: int
    application_name: str | None
    status: ApplicationStatus
    submitted_at: datetime
    updated_at: datetime
    created_by: str
    last_event_type: ValidationEventType | None
    last_event_at: datetime | None


class ApplicationHistoryListResponse(BaseModel):
    """Paginated Application History list, newest submissions first."""

    items: list[ApplicationHistoryListItem]
    total: int
    offset: int
    limit: int


class TimelineEvent(BaseModel):
    """One event on an application's lifecycle timeline.

    ``kind`` is a stable machine-readable category (``APPLICATION_CREATED``,
    ``DOCUMENT_UPLOADED``, ``DOCUMENTS_REQUESTED``, ``DOCUMENTS_RECEIVED``,
    ``SUBMITTED_FOR_PROCESSING``, ``PROCESSING_COMPLETED``,
    ``REVIEW_DECISION``); ``label`` is the human-readable summary shown in the
    UI. Detail strings are assembled server-side from structured fields (never
    raw JSON or extracted content).

    For ``DOCUMENT_UPLOADED`` events, structured fields provide reliable metadata:
    - document_type: the DocumentType enum value
    - copy_number: 1-indexed copy of the document
    - filename: original filename as uploaded
    """

    kind: str
    label: str
    timestamp: datetime
    actor_name: str | None = None
    actor_role: str | None = None
    detail: str | None = None
    document_type: str | None = None
    copy_number: int | None = None
    filename: str | None = None


class ApplicationTimelineResponse(BaseModel):
    """The complete timeline for one application.

    Merges the application's creation, document uploads, operator workflow
    events, processing completion and final review decision into a single
    chronological list, newest last. Review decisions are read from
    ``human_reviews`` (the authoritative record of the final decision) and the
    operator workflow events from ``application_validation_history``.
    """

    application_id: int
    application_name: str | None
    status: ApplicationStatus
    submitted_at: datetime
    created_by: str
    events: list[TimelineEvent]


class ErrorResponse(BaseModel):
    """Envelope used for every Application History error response."""

    detail: str = Field(examples=["Application not found"])