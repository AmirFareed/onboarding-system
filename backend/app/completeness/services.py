"""Completeness verification service.

Verifies that an application's uploaded document metadata satisfies the
configured required/optional catalogue. The service is stateless: every call
reads the current document rows from the database and produces a fresh report,
so reports can never go stale relative to the source of truth.
"""

import logging
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.completeness.constants import (
    ALL_CONFIGURED_DOCUMENT_TYPES,
    OPTIONAL_DOCUMENT_TYPES,
    REQUIRED_DOCUMENT_TYPES,
    CompletenessStatus,
)
from app.completeness.exceptions import ApplicationNotFound
from app.completeness.schemas import (
    CompletenessReport,
    DuplicateDocumentInfo,
    RequiredDocumentStatus,
    UnexpectedDocumentInfo,
)
from app.completeness.validators import validate_document_configuration
from app.database.models.application import Application
from app.database.models.document import Document
from app.database.models.enums import DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.upload.schemas import DocumentMetadata

logger = logging.getLogger(__name__)


class CompletenessService:
    """Verifies an application's document set against the configured catalogue.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        validate_document_configuration()
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)

    def verify(self, *, application_id: int) -> CompletenessReport:
        """Run completeness verification and return a fresh report.

        Args:
            application_id: Id of the application to verify.

        Returns:
            A freshly computed completeness report.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        application = self._get_application(application_id)
        logger.info(
            "Completeness verification started for application id=%s",
            application_id,
        )
        try:
            report = self._build_report(application)
        except Exception:
            logger.exception(
                "Completeness verification failed for application id=%s",
                application_id,
            )
            raise

        self._log_detections(report)
        logger.info(
            "Completeness verification completed for application id=%s: %s",
            application_id,
            report.status.value,
        )
        return report

    def get_report(self, *, application_id: int) -> CompletenessReport:
        """Return the current completeness report.

        The module is stateless, so the report is always recomputed from live
        document metadata and is identical to a fresh verification.

        Args:
            application_id: Id of the application.

        Returns:
            A freshly computed completeness report.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        return self.verify(application_id=application_id)

    def _get_application(self, application_id: int) -> Application:
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _load_documents(self, application_id: int) -> list[Document]:
        """Load every document uploaded for an application."""
        return list(self._documents.get_all_by_application(application_id))

    def _build_report(self, application: Application) -> CompletenessReport:
        """Assemble the report from the application's document metadata."""
        documents = self._load_documents(application.id)
        counts = Counter(document.document_type for document in documents)

        missing = _sorted_values(
            document_type
            for document_type in REQUIRED_DOCUMENT_TYPES
            if counts[document_type] == 0
        )
        duplicates = _sorted_values(
            document_type
            for document_type in REQUIRED_DOCUMENT_TYPES | OPTIONAL_DOCUMENT_TYPES
            if counts[document_type] > 1
        )
        unexpected = _sorted_values(
            document_type
            for document_type in counts
            if document_type not in ALL_CONFIGURED_DOCUMENT_TYPES
        )

        required_statuses = [
            RequiredDocumentStatus(
                document_type=document_type,
                is_present=counts[document_type] > 0,
                copy_count=counts[document_type],
            )
            for document_type in _sorted_values(REQUIRED_DOCUMENT_TYPES)
        ]
        present_required = sum(
            1 for document_type in REQUIRED_DOCUMENT_TYPES if counts[document_type] > 0
        )
        completion_percentage = round(
            100.0 * present_required / len(REQUIRED_DOCUMENT_TYPES),
            2,
        )

        return CompletenessReport(
            application_id=application.id,
            status=self._determine_status(
                missing_documents=missing,
                duplicate_documents=duplicates,
                unexpected_documents=unexpected,
            ),
            uploaded_documents=[DocumentMetadata.model_validate(document) for document in documents],
            required_documents=required_statuses,
            missing_documents=missing,
            duplicate_documents=[
                DuplicateDocumentInfo(
                    document_type=document_type,
                    copy_count=counts[document_type],
                )
                for document_type in duplicates
            ],
            unexpected_documents=[
                UnexpectedDocumentInfo(
                    document_type=document_type,
                    copy_count=counts[document_type],
                )
                for document_type in unexpected
            ],
            completion_percentage=completion_percentage,
            timestamp=datetime.now(UTC),
        )

    def _determine_status(
        self,
        *,
        missing_documents: list[DocumentType],
        duplicate_documents: list[DocumentType],
        unexpected_documents: list[DocumentType],
    ) -> CompletenessStatus:
        """Resolve the overall status, strictest problem first.

        An invalid document set (unexpected types) wins over duplicates, which
        win over missing required documents, which win over completeness.
        """
        if unexpected_documents:
            return CompletenessStatus.INVALID_DOCUMENT_SET
        if duplicate_documents:
            return CompletenessStatus.DUPLICATE_DOCUMENTS
        if missing_documents:
            return CompletenessStatus.INCOMPLETE
        return CompletenessStatus.COMPLETE

    def _log_detections(self, report: CompletenessReport) -> None:
        """Log every detected anomaly in the report."""
        for document_type in report.missing_documents:
            logger.warning(
                "Missing document detected for application id=%s: %s",
                report.application_id,
                document_type.value,
            )
        for duplicate in report.duplicate_documents:
            logger.warning(
                "Duplicate document detected for application id=%s: %s (%s copies)",
                report.application_id,
                duplicate.document_type.value,
                duplicate.copy_count,
            )
        for unexpected in report.unexpected_documents:
            logger.warning(
                "Unexpected document detected for application id=%s: %s (%s copies)",
                report.application_id,
                unexpected.document_type.value,
                unexpected.copy_count,
            )


def _sorted_values(document_types: Iterable[DocumentType]) -> list[DocumentType]:
    """Return document types ordered by their enum value for stable output."""
    return sorted(document_types, key=lambda document_type: document_type.value)
