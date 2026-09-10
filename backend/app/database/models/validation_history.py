"""Validation history model.

Append-only record of application-level validation workflow events. This table
records the operator/reviewer workflow that actually runs: documents requested,
documents received, operator submissions and rejections, processing failures
and final review decisions. Each row captures the actor, the status before and after the
event, the missing documents at that point and any comment, so repeated
document submissions preserve their full history instead of overwriting it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import ApplicationStatus, ValidationEventType

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.user import User


class ValidationHistoryEntry(Base):
    """One application-level validation workflow event.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Related application.
        event_type: What happened.
        actor_id: Acting user, if known (``SET NULL`` on delete).
        actor_name: Acting user's display name, denormalized for history.
        actor_role: Acting user's role at the time, denormalized for history.
        previous_status: Application status before the event, if any.
        new_status: Application status after the event, if any.
        missing_document_types: Document types missing at that point, if any.
        document_ids: Related document ids, if any.
        reason: Free-form reason/comment supplied with the event, if any.
        created_at: When the event occurred (UTC).
    """

    __tablename__ = "application_validation_history"
    __table_args__ = (
        Index(
            "ix_application_validation_history_application_created",
            "application_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[ValidationEventType] = mapped_column(
        nullable=False,
        default=ValidationEventType.DOCUMENTS_REQUESTED,
        server_default="DOCUMENTS_REQUESTED",
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    previous_status: Mapped[ApplicationStatus | None] = mapped_column(nullable=True)
    new_status: Mapped[ApplicationStatus | None] = mapped_column(nullable=True)
    missing_document_types: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    document_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    application: Mapped[Application] = relationship(back_populates="validation_history")
    actor: Mapped[User | None] = relationship(back_populates="validation_history")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ValidationHistoryEntry id={self.id} event={self.event_type}>"