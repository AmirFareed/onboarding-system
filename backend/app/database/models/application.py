"""Application model.

Represents one verification request, the central aggregate root of the system.
Every document, validation result, human review, checklist item, audit record
and feedback entry belongs to an application. All child relationships use
database-level cascade rules so integrity is enforced by PostgreSQL itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import ApplicationStatus

if TYPE_CHECKING:
    from app.database.models.audit_log import AuditLog
    from app.database.models.document import Document
    from app.database.models.feedback_dataset import FeedbackEntry
    from app.database.models.human_review import HumanReview
    from app.database.models.manual_checklist import ManualChecklist
    from app.database.models.queue_job import QueueJob
    from app.database.models.validation_history import ValidationHistoryEntry
    from app.database.models.validation_result import ValidationResult


class Application(Base):
    """A single verification request submitted to the system.

    Attributes:
        id: Auto-incrementing primary key.
        status: Current lifecycle state of the application.
        submitted_at: When the application was first recorded (UTC).
        updated_at: When the application was last modified (UTC).
        created_by: Identifier of the user who submitted the application.
        name: Display name derived from the first uploaded PDF filename
            (e.g. ``TMA Khal Dir Lower``), set at upload time when the
            application has no name yet.
        notes: Free-form notes attached to the application.
        reviewer_comments: Reviewer-edited communication text shown in the
            printable validation report. When null the report uses a
            generated default based on the application status.
    """

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        default=ApplicationStatus.SUBMITTED,
        server_default=text("'SUBMITTED'"),
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)
    reviewer_comments: Mapped[str | None] = mapped_column(Text)

    documents: Mapped[list[Document]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    validation_results: Mapped[list[ValidationResult]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    human_reviews: Mapped[list[HumanReview]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    checklist_items: Mapped[list[ManualChecklist]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="application",
        passive_deletes=True,
    )
    feedback_entries: Mapped[list[FeedbackEntry]] = relationship(
        back_populates="application",
        passive_deletes=True,
    )
    queue_jobs: Mapped[list[QueueJob]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    validation_history: Mapped[list[ValidationHistoryEntry]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Application id={self.id} status={self.status}>"
