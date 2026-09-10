"""Queue job model.

Represents one unit of work in the persistent bulk processing queue: process one
already-ingested document through the existing verification pipeline. Jobs are
deliberately separate rows from the ``documents`` table so the queue lifecycle
(claims, attempts, retries, worker ownership) never mutates document metadata.

The queue is PostgreSQL-backed: row-level locking (``SELECT ... FOR UPDATE SKIP
LOCKED`` in the repository) guarantees two workers can never claim the same job,
and the unique ``document_id`` guarantees a document can never be queued twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import JobStatus, JobType

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.document import Document


class QueueJob(Base):
    """One queued document waiting for (or going through) processing.

    Attributes:
        id: Auto-incrementing unique job id.
        application_id: Owning application (foreign key, cascades on delete).
        document_id: Document this job processes (unique, cascades on delete).
            ``NULL`` for ``APPLICATION_PIPELINE`` jobs, which act on the whole
            application rather than one document.
        job_type: What kind of work this job performs.
        status: Current lifecycle state of the job.
        attempts: Number of processing attempts already performed.
        max_attempts: Attempt budget before the job is permanently failed.
        worker_id: Identifier of the worker currently claiming the job.
        last_error: Most recent failure message (safe, log-friendly detail).
        created_at: When the job was enqueued (UTC).
        started_at: Liveness lease for the current PROCESSING attempt (UTC).
            Refreshed periodically as a heartbeat while a worker owns the job
            (see ``QueueJobRepository.heartbeat``), so it drifts forward
            during a long-running job -- it answers "is the worker still
            alive", not "when did this attempt truly begin". Use
            ``claimed_at`` for real elapsed-processing-time calculations.
        claimed_at: When the current attempt was actually claimed (UTC). Set
            once per claim, alongside ``started_at``, but never touched by
            the heartbeat -- the correct start bound for measuring how long
            an attempt actually took.
        completed_at: When the job reached a terminal state (UTC).
        retry_at: Earliest time a ``RETRY_WAITING`` job may be claimed again.
    """

    __tablename__ = "queue_jobs"
    __table_args__ = (
        Index("ix_queue_jobs_status", "status"),
        Index("ix_queue_jobs_application_id", "application_id"),
        Index("ix_queue_jobs_retry_at", "retry_at"),
        #: A document can be queued exactly once.
        Index("uq_queue_jobs_document_id", "document_id", unique=True),
        #: An application can have at most one pipeline job. This is what
        #: actually guarantees exactly-once enqueueing when two workers detect
        #: "every document job is terminal" at nearly the same time -- see
        #: QueueJobRepository.try_enqueue_pipeline_job.
        Index(
            "uq_queue_jobs_application_pipeline",
            "application_id",
            unique=True,
            postgresql_where=text("job_type = 'APPLICATION_PIPELINE'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    job_type: Mapped[JobType] = mapped_column(
        default=JobType.DOCUMENT_OCR,
        server_default=text("'DOCUMENT_OCR'"),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        default=JobStatus.QUEUED,
        server_default=text("'QUEUED'"),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        default=0,
        server_default="0",
        nullable=False,
    )
    max_attempts: Mapped[int] = mapped_column(
        default=3,
        server_default="3",
        nullable=False,
    )
    worker_id: Mapped[str | None] = mapped_column(String(255))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped[Application] = relationship(back_populates="queue_jobs")
    document: Mapped[Document | None] = relationship(back_populates="queue_jobs")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<QueueJob id={self.id} document_id={self.document_id} status={self.status}>"
