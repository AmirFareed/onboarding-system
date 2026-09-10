"""Pydantic schemas for the Performance API.

Every metric is evidence-backed: each aggregate is accompanied by the
individual time spans that produced it, so the UI can drill from a headline
number down to the exact request/receipt pair, job run or review that
accounts for it.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.database.models.enums import ApplicationStatus


class TimeSpan(BaseModel):
    """One time span contributing to a performance metric.

    ``end`` and ``duration_seconds`` are ``None`` for an open span (e.g. an
    unmatched document request that is still waiting, or a review that has not
    been decided yet). Open spans are still shown as evidence, just never
    counted as closed duration.
    """

    label: str
    start: datetime
    end: datetime | None = None
    duration_seconds: int | None = None
    open: bool = False
    detail: str | None = None


class ApplicationPerformance(BaseModel):
    """Per-application timing breakdown with supporting evidence.

    Timing conventions (all derived from recorded timestamps, never inferred):
    - waiting for documents: each DOCUMENTS_REQUESTED event paired with the
      following DOCUMENTS_RECEIVED event; an unmatched request is an open span.
    - internal processing: each queue job's active span (started_at ->
      completed_at, or -> now while PROCESSING).
    - review: the span from pipeline completion (PENDING_REVIEW) to the latest
      review decision, or to now while still pending.
    - total turnaround: first submission -> latest decision, or to now while
      in flight.
    """

    application_id: int
    application_name: str | None
    status: ApplicationStatus
    submitted_at: datetime
    decided_at: datetime | None = None
    created_by: str

    waiting_seconds: int | None = None
    processing_seconds: int | None = None
    review_seconds: int | None = None
    total_turnaround_seconds: int | None = None
    turnaround_so_far_seconds: int | None = None

    resubmissions: int = 0
    missing_document_cycles: int = 0

    waiting_spans: list[TimeSpan] = []
    processing_spans: list[TimeSpan] = []
    review_spans: list[TimeSpan] = []

    current_state: str | None = None
    current_evidence: str | None = None


class PerformanceOverview(BaseModel):
    """Aggregate performance figures across all applications.

    Averages are computed only over applications that actually have the metric
    (e.g. turnaround is averaged over decided applications only) so a set of
    all-in-flight applications reports no misleading "0 days" turnaround.
    """

    model_config = ConfigDict(from_attributes=True)

    total_applications: int
    decided_applications: int
    status_counts: dict[str, int]

    avg_waiting_seconds: float | None = None
    avg_processing_seconds: float | None = None
    avg_review_seconds: float | None = None
    avg_turnaround_seconds: float | None = None

    total_resubmissions: int
    total_missing_document_cycles: int


class PerformanceApplicationsResponse(BaseModel):
    """Paginated per-application performance rows."""

    items: list[ApplicationPerformance]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    """Envelope used for every Performance error response."""

    detail: str