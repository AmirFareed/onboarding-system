"""Pydantic schemas for the persistent bulk queue API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import JobStatus


class CompletenessSummary(BaseModel):
    """Snapshot of the completeness check run before expensive processing."""

    status: str
    missing_documents: list[str] = Field(default_factory=list)
    completion_percentage: float


class QueueJobRead(BaseModel):
    """Public queue job metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    document_id: int
    status: JobStatus
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_at: datetime | None = None


class EnqueueResponse(BaseModel):
    """Response returned after enqueueing eligible uploaded documents."""

    message: str = Field(examples=["Documents enqueued successfully"])
    application_id: int
    jobs_created: int
    jobs_existing: int
    total_jobs: int
    jobs: list[QueueJobRead]
    completeness: CompletenessSummary | None = None


class QueueProgressResponse(BaseModel):
    """Application-level queue progress."""

    application_id: int
    total: int
    queued: int
    processing: int
    completed: int
    failed: int
    retry_waiting: int


class ProcessingProgressResponse(BaseModel):
    """Operator-facing application processing progress."""

    application_id: int
    total_documents: int
    queued: int
    processing: int
    completed: int
    failed: int
    progress_percentage: float
    documents_needing_attention: int


class ProcessingDocumentResponse(BaseModel):
    """Operator-facing status for one uploaded document."""

    document_id: int
    file_name: str
    status: str
    message: str
    updated_at: datetime | None = None


class ProcessingDocumentsResponse(BaseModel):
    """Statuses for all documents in an application."""

    application_id: int
    documents: list[ProcessingDocumentResponse]


class ProcessingActionResponse(BaseModel):
    """Result of starting or retrying application processing."""

    message: str
    application_id: int
    documents_queued: int
    documents_already_in_progress: int
    documents_retried: int = 0
    completeness: CompletenessSummary | None = None


class QueueStatsResponse(BaseModel):
    """System-wide queue backlog snapshot for operator/ops monitoring."""

    total_queued: int
    total_processing: int
    total_failed: int
    oldest_queued_age_seconds: float | None = None


class WorkerRunResponse(BaseModel):
    """Summary from an explicit worker drain request."""

    workers: int
    processed: int
    succeeded: int
    failed: int
    retried: int


class ErrorResponse(BaseModel):
    """Uniform error envelope."""

    detail: str
