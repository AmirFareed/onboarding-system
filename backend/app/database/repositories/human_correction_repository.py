"""Repository for the HumanCorrection entity."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.human_correction import HumanCorrection
from app.database.repositories.base import BaseRepository


class HumanCorrectionRepository(BaseRepository[HumanCorrection]):
    """Persistence operations for :class:`HumanCorrection`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[HumanCorrection]:
        return HumanCorrection

    def create(
        self,
        *,
        review_id: int,
        field_name: str,
        corrected_value: str,
        document_id: int | None = None,
        original_value: str | None = None,
        reason: str | None = None,
    ) -> HumanCorrection:
        """Create and persist a new field correction attached to a review.

        Args:
            review_id: Review that produced the correction.
            field_name: Name of the corrected field.
            corrected_value: Value confirmed by the reviewer.
            document_id: Document the corrected field was extracted from,
                when known.
            original_value: Value extracted before the correction, if known.
            reason: Optional explanation for the correction.

        Returns:
            The persisted correction.
        """
        correction = HumanCorrection(
            review_id=review_id,
            field_name=field_name,
            document_id=document_id,
            original_value=original_value,
            corrected_value=corrected_value,
            reason=reason,
        )
        self._db.add(correction)
        return self._commit_and_refresh(correction)

    def get_by_review(self, review_id: int) -> Sequence[HumanCorrection]:
        """Return the corrections attached to a review.

        Args:
            review_id: Review id to look up.

        Returns:
            A sequence of corrections ordered by primary key.
        """
        statement = (
            select(HumanCorrection)
            .where(HumanCorrection.review_id == review_id)
            .order_by(HumanCorrection.id)
        )
        return self._db.scalars(statement).all()
