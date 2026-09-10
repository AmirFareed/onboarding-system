"""Repository for the VisualDetection entity."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.document import Document
from app.database.models.visual_detection import VisualDetection
from app.database.repositories.base import BaseRepository


class VisualDetectionRepository(BaseRepository[VisualDetection]):
    """Persistence operations for :class:`VisualDetection`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[VisualDetection]:
        return VisualDetection

    def upsert(
        self,
        *,
        document_id: int,
        detection_type: str,
        is_present: bool,
        confidence: float | None = None,
        detection_engine: str | None = None,
        detected_at: datetime | None = None,
    ) -> VisualDetection:
        """Create or refresh the detection row for a document and kind.

        A document has at most one detection row per kind (unique constraint);
        re-running detection replaces the previous outcome, so the stored row
        always reflects the latest detection run.

        Args:
            document_id: Document that was inspected.
            detection_type: Kind of detection (e.g. ``SIGNATURE``, ``STAMP``).
            is_present: Whether the detection kind was found.
            confidence: Detection confidence reported by the engine.
            detection_engine: Identifier of the engine that produced the result.
            detected_at: When the detection completed.

        Returns:
            The persisted (created or updated) detection row.
        """
        detection = self.get_by_document_and_type(document_id, detection_type)
        if detection is None:
            detection = VisualDetection(
                document_id=document_id,
                detection_type=detection_type,
            )
            self._db.add(detection)
        detection.is_present = is_present
        detection.confidence = confidence
        detection.detection_engine = detection_engine
        if detected_at is not None:
            detection.detected_at = detected_at
        return self._commit_and_refresh(detection)

    def get_by_document_and_type(
        self,
        document_id: int,
        detection_type: str,
    ) -> VisualDetection | None:
        """Return the detection row for a document and kind, or ``None``.

        Args:
            document_id: Document id to look up.
            detection_type: Detection kind to look up.

        Returns:
            The matching detection row or ``None``.
        """
        statement = select(VisualDetection).where(
            VisualDetection.document_id == document_id,
            VisualDetection.detection_type == detection_type,
        )
        return self._db.scalars(statement).first()

    def get_by_document(self, document_id: int) -> Sequence[VisualDetection]:
        """Return every detection row for a document.

        Args:
            document_id: Document id to look up.

        Returns:
            A sequence of detection rows.
        """
        statement = (
            select(VisualDetection)
            .where(VisualDetection.document_id == document_id)
            .order_by(VisualDetection.detection_type)
        )
        return self._db.scalars(statement).all()

    def get_by_application(self, application_id: int) -> Sequence[VisualDetection]:
        """Return every detection row of every document in an application.

        Args:
            application_id: Application id to look up.

        Returns:
            A sequence of detection rows ordered by document and kind.
        """
        statement = (
            select(VisualDetection)
            .join(Document, Document.id == VisualDetection.document_id)
            .where(Document.application_id == application_id)
            .order_by(VisualDetection.document_id, VisualDetection.detection_type)
        )
        return self._db.scalars(statement).all()
