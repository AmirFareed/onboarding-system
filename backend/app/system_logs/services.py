"""Service layer for the IT system-log API."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.database.repositories.audit_log_repository import AuditLogRepository
from app.system_logs.schemas import SystemLogRead


class SystemLogService:
    """Reads the shared audit log for the IT role.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._logs = AuditLogRepository(db)

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
        include_orphaned: bool = False,
    ) -> tuple[list[SystemLogRead], int]:
        """Return matching system logs, newest first.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.
            application_id: Only logs for this application.
            actor: Only logs whose actor username matches.
            event_type: Only logs whose action matches.
            severity: Only logs with this severity.
            date_from: Only logs on/after this timestamp.
            date_to: Only logs before this timestamp.
            query: Free-text match against username/action.
            include_orphaned: When ``False`` (the default), excludes entries
                whose application was later deleted -- the audit trail is
                deliberately kept (not cascaded away) but has nothing left to
                point back to, which otherwise floods this view with entries
                an IT reviewer can't act on. Pass ``True`` to see everything.

        Returns:
            A tuple of matching entries (newest first) and the total count.
        """
        rows, total = self._logs.search(
            offset=offset,
            limit=limit,
            application_id=application_id,
            actor=actor,
            event_type=event_type,
            severity=severity,
            date_from=date_from,
            date_to=date_to,
            query=query,
            include_orphaned=include_orphaned,
        )
        return [SystemLogRead.model_validate(row) for row in rows], total

    def get(self, *, log_id: int) -> SystemLogRead:
        """Return a single system log entry by id."""
        row = self._logs.get_by_id(log_id)
        if row is None:
            raise SystemLogNotFound()
        return SystemLogRead.model_validate(row)


class SystemLogNotFound(Exception):
    """The requested log entry does not exist."""

    status_code = 404
    detail = "System log entry not found"