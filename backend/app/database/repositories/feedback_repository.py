"""Repository for the FeedbackEntry entity."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.database.models.document import Document
from app.database.models.enums import DocumentType
from app.database.models.feedback_dataset import FeedbackEntry
from app.database.repositories.base import BaseRepository


class FeedbackRepository(BaseRepository[FeedbackEntry]):
    """Persistence operations for :class:`FeedbackEntry`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[FeedbackEntry]:
        return FeedbackEntry

    def create(
        self,
        *,
        application_id: int | None,
        field_name: str,
        human_value: str,
        ocr_value: str | None = None,
        confidence_score: float | None = None,
        document_id: int | None = None,
        ocr_result_id: int | None = None,
        normalized_value: str | None = None,
        confidence_source: str | None = None,
        correction_reason: str | None = None,
        reviewer: str | None = None,
        decision: str | None = None,
        origin: str | None = None,
        commit: bool = True,
    ) -> FeedbackEntry:
        """Create and persist a new feedback dataset sample.

        Args:
            application_id: Source application, if known.
            field_name: Name of the field the sample describes.
            human_value: Value confirmed/corrected by a human reviewer.
            ocr_value: Value extracted by the OCR pipeline, if available.
            confidence_score: Confidence the OCR pipeline assigned.
            document_id: Document the corrected field was extracted from.
            ocr_result_id: OCR result the corrected field belongs to.
            normalized_value: Canonical form of the value, if normalized.
            confidence_source: Source that produced the confidence score.
            correction_reason: Optional explanation for the correction.
            reviewer: Name of the reviewer who corrected the field.
            decision: Review decision that produced the correction.
            origin: Whether the correction came from a low-confidence review
                or the final human review.
            commit: When ``False``, adds and flushes the entry but defers the
                commit to the caller so it shares the caller's transaction
                (used when a surrounding service needs the feedback write to be
                atomic with an audit write). Defaults to ``True`` for the
                repository's self-contained-transaction contract.

        Returns:
            The persisted feedback entry.
        """
        entry = FeedbackEntry(
            application_id=application_id,
            field_name=field_name,
            human_value=human_value,
            ocr_value=ocr_value,
            confidence_score=confidence_score,
            document_id=document_id,
            ocr_result_id=ocr_result_id,
            normalized_value=normalized_value,
            confidence_source=confidence_source,
            correction_reason=correction_reason,
            reviewer=reviewer,
            decision=decision,
            origin=origin,
        )
        self._db.add(entry)
        if not commit:
            self._db.flush()
            return entry
        return self._commit_and_refresh(entry)

    def count(self) -> int:
        """Return the total number of feedback samples."""
        return self._db.scalar(select(func.count(FeedbackEntry.id))) or 0

    def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[FeedbackEntry]:
        """Return feedback samples, most recently recorded first.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of feedback entries.
        """
        statement = (
            select(FeedbackEntry)
            .order_by(FeedbackEntry.recorded_at.desc(), FeedbackEntry.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return self._db.scalars(statement).all()

    def list_matching(
        self,
        *,
        application_id: int | None = None,
        reviewer: str | None = None,
        document_type: DocumentType | None = None,
        field_name: str | None = None,
        decision: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_confidence: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[FeedbackEntry]:
        """Return feedback samples matching the given filters, newest first.

        Args:
            application_id: Only entries for this application.
            reviewer: Only entries corrected by this reviewer.
            document_type: Only entries whose source document is of this type.
            field_name: Only entries for this field.
            decision: Only entries produced by this decision.
            date_from: Only entries recorded at or after this instant.
            date_to: Only entries recorded at or before this instant.
            min_confidence: Only entries with confidence at least this value.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of matching feedback entries.
        """
        statement = (
            self._matching_statement(
                application_id=application_id,
                reviewer=reviewer,
                document_type=document_type,
                field_name=field_name,
                decision=decision,
                date_from=date_from,
                date_to=date_to,
                min_confidence=min_confidence,
            )
            .offset(offset)
            .limit(limit)
        )
        return self._db.scalars(statement).all()

    def count_matching(
        self,
        *,
        application_id: int | None = None,
        reviewer: str | None = None,
        document_type: DocumentType | None = None,
        field_name: str | None = None,
        decision: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_confidence: float | None = None,
    ) -> int:
        """Count feedback samples matching the given filters."""
        statement = self._matching_statement(
            application_id=application_id,
            reviewer=reviewer,
            document_type=document_type,
            field_name=field_name,
            decision=decision,
            date_from=date_from,
            date_to=date_to,
            min_confidence=min_confidence,
        ).order_by(None).with_only_columns(func.count(FeedbackEntry.id))
        return self._db.scalar(statement) or 0

    def all_matching(
        self,
        *,
        application_id: int | None = None,
        reviewer: str | None = None,
        document_type: DocumentType | None = None,
        field_name: str | None = None,
        decision: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_confidence: float | None = None,
    ) -> Sequence[FeedbackEntry]:
        """Return every feedback sample matching the given filters.

        Used by the statistics and export flows which operate over the full
        matching population rather than a single page.
        """
        return self._db.scalars(
            self._matching_statement(
                application_id=application_id,
                reviewer=reviewer,
                document_type=document_type,
                field_name=field_name,
                decision=decision,
                date_from=date_from,
                date_to=date_to,
                min_confidence=min_confidence,
            )
        ).all()

    def document_types(self, document_ids: Sequence[int]) -> dict[int, DocumentType]:
        """Map document ids to their document type.

        Args:
            document_ids: Document ids to resolve.

        Returns:
            A mapping of the given ids that exist to their document type.
        """
        if not document_ids:
            return {}
        rows = self._db.execute(
            select(Document.id, Document.document_type).where(
                Document.id.in_(set(document_ids))
            )
        ).all()
        return {row.id: row.document_type for row in rows}

    def _matching_statement(
        self,
        *,
        application_id: int | None = None,
        reviewer: str | None = None,
        document_type: DocumentType | None = None,
        field_name: str | None = None,
        decision: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_confidence: float | None = None,
    ) -> Select:
        """Build the filtered select, newest recorded first."""
        statement = select(FeedbackEntry).order_by(
            FeedbackEntry.recorded_at.desc(),
            FeedbackEntry.id.desc(),
        )
        if application_id is not None:
            statement = statement.where(FeedbackEntry.application_id == application_id)
        if reviewer is not None:
            statement = statement.where(FeedbackEntry.reviewer == reviewer)
        if document_type is not None:
            statement = statement.join(Document, Document.id == FeedbackEntry.document_id)
            statement = statement.where(Document.document_type == document_type)
        if field_name is not None:
            statement = statement.where(FeedbackEntry.field_name == field_name)
        if decision is not None:
            statement = statement.where(FeedbackEntry.decision == decision)
        if date_from is not None:
            statement = statement.where(FeedbackEntry.recorded_at >= date_from)
        if date_to is not None:
            statement = statement.where(FeedbackEntry.recorded_at <= date_to)
        if min_confidence is not None:
            statement = statement.where(FeedbackEntry.confidence_score >= min_confidence)
        return statement
