"""Repository for the AuditLog entity."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database.models.audit_log import AuditLog
from app.database.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Persistence operations for :class:`AuditLog`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[AuditLog]:
        return AuditLog

    def create(
        self,
        *,
        application_id: int | None,
        username: str,
        action: str,
        details: dict[str, Any] | None = None,
        actor_id: int | None = None,
        actor_role: str | None = None,
        document_id: int | None = None,
        severity: str | None = None,
        previous_status: str | None = None,
        new_status: str | None = None,
        commit: bool = True,
    ) -> AuditLog:
        """Create and persist a new audit log entry.

        Args:
            application_id: Related application, if any.
            username: Identity of the user who performed the action.
            action: Machine-readable action identifier.
            details: Structured JSON context describing the action.
            actor_id: Acting user id, if known.
            actor_role: Acting user's role, if known.
            document_id: Related document, if any.
            severity: Severity/category of the event.
            previous_status: Application status before the event, if any.
            new_status: Application status after the event, if any.
            commit: When ``False``, adds and flushes the entry but defers the
                commit to the caller so it shares the caller's transaction.
                Used by services that need the audit write to be atomic with a
                business-data mutation. Defaults to ``True`` for the
                repository's self-contained-transaction contract.

        Returns:
            The persisted audit log entry.
        """
        entry = AuditLog(
            application_id=application_id,
            username=username,
            action=action,
            details=details,
            actor_id=actor_id,
            actor_role=actor_role,
            document_id=document_id,
            severity=severity,
            previous_status=previous_status,
            new_status=new_status,
        )
        self._db.add(entry)
        if not commit:
            self._db.flush()
            return entry
        return self._commit_and_refresh(entry)

    def search(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        application_id: int | None = None,
        actor: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        query: str | None = None,
        include_orphaned: bool = True,
    ) -> tuple[list[AuditLog], int]:
        """Return audit log entries matching the given filters, newest first.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.
            application_id: Only logs for this application.
            actor: Only logs whose username matches (case-insensitive substring).
            event_type: Only logs whose action matches (exact).
            severity: Only logs with this severity.
            date_from: Only logs on/after this timestamp (inclusive).
            date_to: Only logs before this timestamp (exclusive).
            query: Free-text substring match against username/action/details.
            include_orphaned: When ``False``, excludes entries whose
                ``application_id`` is ``NULL`` -- left behind when the
                application they were recorded against was later deleted
                (``ON DELETE SET NULL``), which preserves the audit trail but
                leaves it with no application to point back to. Defaults to
                ``True`` (unfiltered) so this is opt-in, not a behavior change
                for any existing caller.

        Returns:
            A tuple of matching entries (newest first) and the total count.
        """
        statement = self._apply_filters(
            select(AuditLog),
            application_id=application_id,
            actor=actor,
            event_type=event_type,
            severity=severity,
            date_from=date_from,
            date_to=date_to,
            query=query,
            include_orphaned=include_orphaned,
        )
        count = len(self._db.scalars(statement.order_by(AuditLog.id)).all())
        statement = statement.order_by(
            AuditLog.performed_at.desc(), AuditLog.id.desc()
        ).offset(offset).limit(limit)
        return list(self._db.scalars(statement).all()), count

    def _apply_filters(
        self,
        statement: Select,
        *,
        application_id: int | None,
        actor: str | None,
        event_type: str | None,
        severity: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        query: str | None,
        include_orphaned: bool = True,
    ) -> Select:
        """Apply the search filters to a select statement."""
        if application_id is not None:
            statement = statement.where(AuditLog.application_id == application_id)
        if not include_orphaned:
            statement = statement.where(AuditLog.application_id.isnot(None))
        if actor:
            statement = statement.where(AuditLog.username.ilike(f"%{actor}%"))
        if event_type:
            statement = statement.where(AuditLog.action == event_type)
        if severity:
            statement = statement.where(AuditLog.severity == severity)
        if date_from is not None:
            statement = statement.where(AuditLog.performed_at >= date_from)
        if date_to is not None:
            statement = statement.where(AuditLog.performed_at < date_to)
        if query:
            statement = statement.where(
                (AuditLog.username.ilike(f"%{query}%"))
                | (AuditLog.action.ilike(f"%{query}%"))
            )
        return statement