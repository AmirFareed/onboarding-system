"""Repository for the ExtractedField entity."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.document import Document
from app.database.models.extracted_field import ExtractedField
from app.database.models.ocr_result import OCRResult
from app.database.repositories.base import BaseRepository


class ExtractedFieldRepository(BaseRepository[ExtractedField]):
    """Persistence operations for :class:`ExtractedField`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[ExtractedField]:
        return ExtractedField

    def upsert(
        self,
        *,
        ocr_result_id: int,
        field_name: str,
        extracted_value: str,
        confidence_score: float | None,
        confidence_source: str | None,
        confidence_reason: str | None,
        verification_status: str | None,
        normalized_value: str | None = None,
        commit: bool = True,
    ) -> ExtractedField:
        """Create or refresh the field row keyed on the OCR result and name.

        A field is uniquely identified by its OCR result and field name; running
        the confidence evaluation again replaces the scoring columns without
        ever touching the human-verification state, so a completed review is
        never silently overwritten by a re-evaluation.

        Args:
            ocr_result_id: Owning OCR result of the analysed document.
            field_name: Machine-readable name of the field.
            extracted_value: Value produced by the extraction engine.
            confidence_score: Computed field confidence (0.0 - 1.0).
            confidence_source: Source that produced the score.
            confidence_reason: Human-readable explanation of the score.
            verification_status: Per-field verification state.
            normalized_value: Canonical form of the value, if available.
            commit: When ``False``, adds/mutates and flushes the row but defers
                the commit to the caller so it shares the caller's transaction
                (used when a surrounding service needs the field write to be
                atomic with an audit write). Defaults to ``True`` for the
                repository's self-contained-transaction contract.

        Returns:
            The persisted (created or updated) field row.
        """
        field = self.get_by_ocr_result_and_name(ocr_result_id, field_name)
        if field is None:
            field = ExtractedField(
                ocr_result_id=ocr_result_id,
                field_name=field_name,
                extracted_value=extracted_value,
            )
            self._db.add(field)
        field.extracted_value = extracted_value
        field.confidence_score = confidence_score
        field.confidence_source = confidence_source
        field.confidence_reason = confidence_reason
        field.verification_status = verification_status
        field.normalized_value = normalized_value
        if not commit:
            self._db.flush()
            return field
        return self._commit_and_refresh(field)

    def get_by_ocr_result_and_name(
        self,
        ocr_result_id: int,
        field_name: str,
    ) -> ExtractedField | None:
        """Return the field row for an OCR result and name, or ``None``.

        Args:
            ocr_result_id: Owning OCR result id.
            field_name: Field name to look up.

        Returns:
            The matching field row or ``None``.
        """
        statement = select(ExtractedField).where(
            ExtractedField.ocr_result_id == ocr_result_id,
            ExtractedField.field_name == field_name,
        )
        return self._db.scalars(statement).first()

    def get_by_application(self, application_id: int) -> Sequence[ExtractedField]:
        """Return the evaluated fields of every document in an application.

        Fields are reached through their OCR result and the owning document, so
        only rows belonging to the application are returned, ordered by document
        and field name for a deterministic review list.

        Args:
            application_id: Application id to look up.

        Returns:
            A sequence of extracted field rows.
        """
        statement = (
            select(ExtractedField)
            .join(OCRResult, OCRResult.id == ExtractedField.ocr_result_id)
            .join(Document, Document.id == OCRResult.document_id)
            .where(Document.application_id == application_id)
            .order_by(OCRResult.document_id, ExtractedField.field_name)
        )
        return self._db.scalars(statement).all()
