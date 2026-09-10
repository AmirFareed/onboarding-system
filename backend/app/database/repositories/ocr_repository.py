"""Repository for the OCRResult entity."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.document import Document
from app.database.models.ocr_result import OCRResult
from app.database.repositories.base import BaseRepository


class OCRRepository(BaseRepository[OCRResult]):
    """Persistence operations for :class:`OCRResult`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[OCRResult]:
        return OCRResult

    def create(
        self,
        *,
        document_id: int,
        raw_ocr_text: str,
        ocr_engine: str,
        processing_time_ms: int | None = None,
        overall_confidence: float | None = None,
    ) -> OCRResult:
        """Create and persist a new OCR result for a document.

        Args:
            document_id: Document that was processed.
            raw_ocr_text: Full raw text produced by the OCR engine.
            ocr_engine: Identifier of the OCR engine used.
            processing_time_ms: Duration of the OCR run in milliseconds.
            overall_confidence: Engine-reported confidence for the document.

        Returns:
            The persisted OCR result.
        """
        ocr_result = OCRResult(
            document_id=document_id,
            raw_ocr_text=raw_ocr_text,
            ocr_engine=ocr_engine,
            processing_time_ms=processing_time_ms,
            overall_confidence=overall_confidence,
        )
        self._db.add(ocr_result)
        return self._commit_and_refresh(ocr_result)

    def get_by_document(self, document_id: int) -> OCRResult | None:
        """Return the OCR result for a document, or ``None``.

        Args:
            document_id: Document id to look up.

        Returns:
            The matching OCR result or ``None``.
        """
        statement = select(OCRResult).where(OCRResult.document_id == document_id)
        return self._db.scalars(statement).first()

    def upsert(
        self,
        *,
        document_id: int,
        raw_ocr_text: str,
        ocr_engine: str,
        processing_time_ms: int | None = None,
        overall_confidence: float | None = None,
        processing_method: str | None = None,
        page_count: int | None = None,
        character_count: int | None = None,
        processed_at: datetime | None = None,
    ) -> OCRResult:
        """Create or refresh the single OCR result for a document.

        A document has at most one OCR result (unique foreign key); re-processing
        the same document replaces the previous text, engine and metrics instead
        of violating the constraint.

        Args:
            document_id: Document that was processed.
            raw_ocr_text: Full raw text produced by the OCR engine.
            ocr_engine: Identifier of the OCR engine used.
            processing_time_ms: Duration of the OCR run in milliseconds.
            overall_confidence: Engine-reported confidence for the document.
            processing_method: How the text was obtained.
            page_count: Number of pages that contributed to the text.
            character_count: Length of the extracted text in characters.
            processed_at: When the extraction completed.

        Returns:
            The persisted (created or updated) OCR result.
        """
        ocr_result = self.get_by_document(document_id)
        if ocr_result is None:
            ocr_result = OCRResult(document_id=document_id)
            self._db.add(ocr_result)
        ocr_result.raw_ocr_text = raw_ocr_text
        ocr_result.ocr_engine = ocr_engine
        ocr_result.processing_time_ms = processing_time_ms
        ocr_result.overall_confidence = overall_confidence
        ocr_result.processing_method = processing_method
        ocr_result.page_count = page_count
        ocr_result.character_count = character_count
        ocr_result.processed_at = processed_at
        return self._commit_and_refresh(ocr_result)

    def get_by_application(self, application_id: int) -> Sequence[OCRResult]:
        """Return the OCR results of every document in an application.

        Args:
            application_id: Application id to look up.

        Returns:
            A sequence of OCR results ordered by document id.
        """
        statement = (
            select(OCRResult)
            .join(Document, Document.id == OCRResult.document_id)
            .where(Document.application_id == application_id)
            .order_by(OCRResult.document_id)
        )
        return self._db.scalars(statement).all()
