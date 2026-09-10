"""Repository for the DocumentAnalysisResult entity."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.document import Document
from app.database.models.document_analysis_result import DocumentAnalysisResult
from app.database.repositories.base import BaseRepository


class DocumentAnalysisRepository(BaseRepository[DocumentAnalysisResult]):
    """Persistence operations for :class:`DocumentAnalysisResult`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[DocumentAnalysisResult]:
        return DocumentAnalysisResult

    def upsert(
        self,
        *,
        application_id: int,
        document_id: int,
        document_type: str,
        extracted_fields: dict,
        validation_results: list,
        consistency_results: list,
        confidence_score: float | None,
        verification_status: str,
        analysis_version: str,
        processing_time_ms: int | None,
    ) -> DocumentAnalysisResult:
        """Create or refresh the single analysis result for a document.

        A document has at most one analysis result (unique foreign key);
        re-analysing the same document replaces the previous extracted fields,
        validations, consistency checks and score instead of violating the
        constraint.

        Args:
            application_id: Owning application id.
            document_id: Analysed document.
            document_type: Detected analysed document category.
            extracted_fields: Normalized fields extracted from the text.
            validation_results: Per-field validation outcomes.
            consistency_results: Cross-field consistency check outcomes.
            confidence_score: Deterministic overall confidence (0.0 - 1.0).
            verification_status: Overall verification status.
            analysis_version: Version of the analysis logic used.
            processing_time_ms: Duration of the analysis in milliseconds.

        Returns:
            The persisted (created or updated) analysis result.
        """
        result = self.get_by_document(document_id)
        if result is None:
            result = DocumentAnalysisResult(
                application_id=application_id,
                document_id=document_id,
            )
            self._db.add(result)
        result.document_type = document_type
        result.extracted_fields = extracted_fields
        result.validation_results = validation_results
        result.consistency_results = consistency_results
        result.confidence_score = confidence_score
        result.verification_status = verification_status
        result.analysis_version = analysis_version
        result.processing_time_ms = processing_time_ms
        return self._commit_and_refresh(result)

    def get_by_document(self, document_id: int) -> DocumentAnalysisResult | None:
        """Return the analysis result for a document, or ``None``.

        Args:
            document_id: Document id to look up.

        Returns:
            The matching analysis result or ``None``.
        """
        statement = select(DocumentAnalysisResult).where(
            DocumentAnalysisResult.document_id == document_id
        )
        return self._db.scalars(statement).first()

    def get_by_application(self, application_id: int) -> Sequence[DocumentAnalysisResult]:
        """Return the analysis results of every document in an application.

        Args:
            application_id: Application id to look up.

        Returns:
            A sequence of analysis results ordered by document id.
        """
        statement = (
            select(DocumentAnalysisResult)
            .join(Document, Document.id == DocumentAnalysisResult.document_id)
            .where(Document.application_id == application_id)
            .order_by(DocumentAnalysisResult.document_id)
        )
        return self._db.scalars(statement).all()
