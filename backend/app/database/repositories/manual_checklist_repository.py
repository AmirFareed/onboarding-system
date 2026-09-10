"""Repository for the ManualChecklist entity."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.manual_checklist import ManualChecklist
from app.database.repositories.base import BaseRepository


class ManualChecklistRepository(BaseRepository[ManualChecklist]):
    """Persistence operations for :class:`ManualChecklist`.

    A checklist item is unique per application (``application_id`` +
    ``item_name``), so recording a review state is an upsert that never creates
    duplicate rows.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[ManualChecklist]:
        return ManualChecklist

    def get_by_application(self, application_id: int) -> Sequence[ManualChecklist]:
        """Return the checklist items recorded for an application.

        Args:
            application_id: Application id to look up.

        Returns:
            A sequence of checklist items ordered by item name.
        """
        statement = (
            select(ManualChecklist)
            .where(ManualChecklist.application_id == application_id)
            .order_by(ManualChecklist.item_name)
        )
        return self._db.scalars(statement).all()

    def get(self, application_id: int, item_name: str) -> ManualChecklist | None:
        """Return one checklist item for an application, or ``None``.

        Args:
            application_id: Application id to look up.
            item_name: Name of the checklist item.

        Returns:
            The matching item or ``None``.
        """
        statement = select(ManualChecklist).where(
            ManualChecklist.application_id == application_id,
            ManualChecklist.item_name == item_name,
        )
        return self._db.scalars(statement).first()

    def upsert(
        self,
        *,
        application_id: int,
        item_name: str,
        is_checked: bool,
        reviewer: str | None = None,
    ) -> ManualChecklist:
        """Create or refresh one checklist item for an application.

        Args:
            application_id: Application the item belongs to.
            item_name: Name of the checklist item.
            is_checked: Whether the reviewer verified the item.
            reviewer: Name of the reviewer who checked the item.

        Returns:
            The persisted item.
        """
        item = self.get(application_id, item_name)
        if item is None:
            item = ManualChecklist(
                application_id=application_id,
                item_name=item_name,
            )
            self._db.add(item)
        item.is_checked = is_checked
        item.reviewer = reviewer
        return self._commit_and_refresh(item)
