"""Repository for the HumanReview entity."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.enums import ReviewDecision
from app.database.models.human_review import HumanReview
from app.database.repositories.base import BaseRepository


class HumanReviewRepository(BaseRepository[HumanReview]):
    """Persistence operations for :class:`HumanReview`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[HumanReview]:
        return HumanReview

    def create(
        self,
        *,
        application_id: int,
        reviewer_name: str,
        decision: ReviewDecision,
        comments: str | None = None,
        rejection_reason: str | None = None,
    ) -> HumanReview:
        """Create and persist a new human review.

        Args:
            application_id: Application being reviewed.
            reviewer_name: Name of the reviewer.
            decision: Approve, correct or reject the application.
            comments: Optional free-form notes.
            rejection_reason: Mandatory explanation for a reject decision.

        Returns:
            The persisted human review.
        """
        review = HumanReview(
            application_id=application_id,
            reviewer_name=reviewer_name,
            decision=decision,
            comments=comments,
            rejection_reason=rejection_reason,
        )
        self._db.add(review)
        return self._commit_and_refresh(review)

    def get_by_application(
        self,
        application_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[HumanReview]:
        """Return human reviews for an application.

        Args:
            application_id: Application id to look up.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of reviews ordered by review date.
        """
        statement = (
            select(HumanReview)
            .where(HumanReview.application_id == application_id)
            .order_by(HumanReview.reviewed_at.desc(), HumanReview.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return self._db.scalars(statement).all()
