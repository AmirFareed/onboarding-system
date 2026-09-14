"""Repository for the Application entity."""

from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.database.models.application import Application
from app.database.models.enums import ApplicationStatus
from app.database.repositories.base import UNSET, BaseRepository, _UnsetType


class ApplicationRepository(BaseRepository[Application]):
    """Persistence operations for :class:`Application`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[Application]:
        return Application

    def create(
        self,
        *,
        created_by: str,
        status: ApplicationStatus = ApplicationStatus.SUBMITTED,
        notes: str | None = None,
    ) -> Application:
        """Create and persist a new application.

        Args:
            created_by: Identifier of the user submitting the application.
            status: Initial application status.
            notes: Optional free-form notes.

        Returns:
            The persisted application with server-generated fields loaded.
        """
        application = Application(
            created_by=created_by,
            status=status,
            notes=notes,
        )
        self._db.add(application)
        return self._commit_and_refresh(application)

    def update(
        self,
        application: Application,
        *,
        status: ApplicationStatus | _UnsetType = UNSET,
        notes: str | _UnsetType | None = UNSET,
    ) -> Application:
        """Apply the provided changes to an application.

        Only arguments that were explicitly passed are applied; ``UNSET``
        fields remain untouched. Pass ``notes=None`` to clear the notes.

        Args:
            application: Application instance to update.
            status: New status, or :data:`UNSET` to leave unchanged.
            notes: New notes (``None`` clears them), or :data:`UNSET`.

        Returns:
            The updated application with server-generated fields loaded.
        """
        if status is not UNSET:
            application.status = status
        if notes is not UNSET:
            application.notes = notes
        self._db.add(application)
        return self._commit_and_refresh(application)

    def update_status_if(
        self,
        application_id: int,
        *,
        new_status: ApplicationStatus,
        allowed_current_statuses: Sequence[ApplicationStatus],
    ) -> bool:
        """Atomically move an application to ``new_status``, but only if its
        current status is still one of ``allowed_current_statuses``.

        Issues a single conditional ``UPDATE ... WHERE id = :id AND status
        IN (...)`` instead of the read-then-write pattern (read a status,
        decide in Python, write it back), which is safe under concurrent
        requests: if another request already moved the application to a
        status outside ``allowed_current_statuses`` (e.g. an operator
        rejection) between this caller's own earlier read and this call, the
        WHERE clause simply matches nothing and the stale transition is
        silently dropped instead of clobbering the newer status.

        Args:
            application_id: Id of the application to update.
            new_status: Status to move the application to.
            allowed_current_statuses: Current statuses from which this
                transition is valid.

        Returns:
            ``True`` if a row was updated, ``False`` if the application's
            current status no longer matched ``allowed_current_statuses``.
        """
        statement = (
            sa_update(Application)
            .where(
                Application.id == application_id,
                Application.status.in_(allowed_current_statuses),
            )
            .values(status=new_status)
        )
        result = self._db.execute(statement)
        self._db.commit()
        return result.rowcount > 0

    def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: ApplicationStatus | None = None,
    ) -> Sequence[Application]:
        """List applications, optionally filtered by status.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.
            status: When given, only return applications in this status.

        Returns:
            A sequence of applications ordered by submission date.
        """
        statement = (
            select(Application)
            .order_by(Application.submitted_at.desc(), Application.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(Application.status == status)
        return self._db.scalars(statement).all()

    def search(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        query: str | None = None,
        status: ApplicationStatus | None = None,
    ) -> tuple[Sequence[Application], int]:
        """Search applications by free-text query, optionally by status.

        The free-text query matches the application id (when the query parses
        as an integer), the display name and the submitter, so IT can find an
        application by ``123``, by ``TMA Khal Dir Lower`` or by the uploader's
        identifier alike.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.
            query: Free-text substring match against id/name/created_by.
            status: When given, only return applications in this status.

        Returns:
            A tuple of matching applications (newest first) and the total count.
        """
        statement = select(Application).order_by(
            Application.submitted_at.desc(), Application.id.desc()
        )
        statement = self._apply_filters(statement, query=query, status=status)
        count_stmt = select(func.count()).select_from(statement.subquery())
        total = self._db.scalar(count_stmt) or 0
        rows = list(self._db.scalars(statement.offset(offset).limit(limit)).all())
        return rows, total

    @staticmethod
    def _apply_filters(
        statement: Select,
        *,
        query: str | None,
        status: ApplicationStatus | None,
    ) -> Select:
        """Apply the search filters to a select statement."""
        if status is not None:
            statement = statement.where(Application.status == status)
        if query:
            conditions = [
                Application.name.ilike(f"%{query}%"),
                Application.created_by.ilike(f"%{query}%"),
            ]
            if query.isdigit():
                conditions.append(Application.id == int(query))
            statement = statement.where(or_(*conditions))
        return statement

    def get_reviewer_comments(self, application_id: int) -> str | None:
        """Return the saved reviewer comment for an application, or None."""
        application = self.get_by_id(application_id)
        if application is None:
            return None
        return application.reviewer_comments

    def save_reviewer_comments(
        self, application_id: int, comments: str | None
    ) -> str | None:
        """Save (or clear) the reviewer comment for an application.

        Trims whitespace. Empty/whitespace-only values are stored as None.

        Args:
            application_id: Id of the application.
            comments: The reviewer comment text, or None to clear.

        Returns:
            The saved comment (or None if cleared).
        """
        application = self.get_by_id(application_id)
        if application is None:
            return None
        trimmed = (comments or "").strip()
        application.reviewer_comments = trimmed or None
        self._db.add(application)
        self._commit_and_refresh(application)
        return application.reviewer_comments

    def get_edited_report_html(self, application_id: int) -> str | None:
        """Return the saved edited report HTML for an application, or None."""
        application = self.get_by_id(application_id)
        if application is None:
            return None
        return application.edited_report_html

    def save_edited_report_html(
        self, application_id: int, html: str | None
    ) -> str | None:
        """Save (or clear) the edited report HTML for an application.

        Trims whitespace. Empty/whitespace-only values are stored as None,
        which reverts the report and PDF download to always regenerating
        fresh from live pipeline data.

        Args:
            application_id: Id of the application.
            html: The edited report HTML, or None to clear.

        Returns:
            The saved HTML (or None if cleared).
        """
        application = self.get_by_id(application_id)
        if application is None:
            return None
        trimmed = (html or "").strip()
        application.edited_report_html = trimmed or None
        self._db.add(application)
        self._commit_and_refresh(application)
        return application.edited_report_html
