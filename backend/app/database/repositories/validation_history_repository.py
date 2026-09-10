"""Repository for application validation history entries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.enums import ValidationEventType
from app.database.models.validation_history import ValidationHistoryEntry
from app.database.repositories.base import BaseRepository


class ValidationHistoryRepository(BaseRepository[ValidationHistoryEntry]):
    """Persistence operations for :class:`ValidationHistoryEntry`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[ValidationHistoryEntry]:
        return ValidationHistoryEntry

    def create(
        self,
        *,
        application_id: int,
        event_type: ValidationEventType,
        actor_id: int | None = None,
        actor_name: str | None = None,
        actor_role: str | None = None,
        previous_status: str | None = None,
        new_status: str | None = None,
        missing_document_types: list[str] | None = None,
        document_ids: list[int] | None = None,
        reason: str | None = None,
    ) -> ValidationHistoryEntry:
        """Append a new history entry for an application.

        Args:
            application_id: Related application.
            event_type: What happened.
            actor_id: Acting user id, if known.
            actor_name: Acting user's display name.
            actor_role: Acting user's role.
            previous_status: Application status before the event.
            new_status: Application status after the event.
            missing_document_types: Document types missing at that point.
            document_ids: Related document ids, if any.
            reason: Free-form comment supplied with the event.

        Returns:
            The persisted history entry.
        """
        entry = ValidationHistoryEntry(
            application_id=application_id,
            event_type=event_type,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=actor_role,
            previous_status=previous_status,
            new_status=new_status,
            missing_document_types=missing_document_types,
            document_ids=document_ids,
            reason=reason,
        )
        self._db.add(entry)
        return self._commit_and_refresh(entry)

    def list_for_application(
        self,
        application_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ValidationHistoryEntry], int]:
        """Return an application's history, newest first.

        Args:
            application_id: The application to list history for.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A tuple of entries (newest first) and the total count.
        """
        statement = (
            select(ValidationHistoryEntry)
            .where(ValidationHistoryEntry.application_id == application_id)
            .order_by(ValidationHistoryEntry.created_at.desc(), ValidationHistoryEntry.id.desc())
        )
        total = len(
            self._db.scalars(
                select(ValidationHistoryEntry.id).where(
                    ValidationHistoryEntry.application_id == application_id
                )
            ).all()
        )
        rows = list(self._db.scalars(statement.offset(offset).limit(limit)).all())
        return rows, total

    def latest_for_application(self, application_id: int) -> ValidationHistoryEntry | None:
        """Return the most recent history entry for an application, if any."""
        statement = (
            select(ValidationHistoryEntry)
            .where(ValidationHistoryEntry.application_id == application_id)
            .order_by(ValidationHistoryEntry.created_at.desc(), ValidationHistoryEntry.id.desc())
            .limit(1)
        )
        return self._db.scalar(statement)