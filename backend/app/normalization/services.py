"""Data normalization service.

Runs every verified extracted field of an application through its configured
normalizer, persists the canonical form into ``normalized_value`` (leaving the
extracted value untouched), and reports the per-field outcome. The actual
canonicalization logic lives in module-level normalizer classes so it can be
unit-tested without a database; the service only decides which value to feed a
field (human-corrected values take precedence), which fields are eligible, and
how the results are stored and reported.
"""

import logging
from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.document_analysis_repository import DocumentAnalysisRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.extracted_field_repository import ExtractedFieldRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.normalization.constants import (
    ACTION_NORMALIZED,
    NORMALIZATION_VERSION,
    NormalizationOutcome,
    NormalizationStatus,
)
from app.normalization.exceptions import ApplicationNotFound, NoExtractedFields
from app.normalization.normalizers import NormalizerRegistry
from app.normalization.schemas import (
    NormalizationSummary,
    NormalizedFieldItem,
    NormalizedFieldRecord,
    NormalizeResponse,
)
from app.normalization.validators import is_verified_for_normalization

logger = logging.getLogger(__name__)


class NormalizationService:
    """Normalizes an application's verified extracted fields.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._ocr_results = OCRRepository(db)
        self._fields = ExtractedFieldRepository(db)
        self._analysis_results = DocumentAnalysisRepository(db)
        self._audit = AuditLogRepository(db)
        self._registry = NormalizerRegistry()

    # -- Public API -----------------------------------------------------------

    def normalize(self, *, application_id: int) -> NormalizeResponse:
        """Normalize every eligible field of an application and persist the result.

        Only fields whose verification status is ``VERIFIED``, ``CORRECTED`` or
        ``AUTO_VERIFIED`` are canonicalized; pending and halted fields are
        reported as skipped. For every field the verified value is the
        human-corrected value when one exists, otherwise the extracted value.
        The ``normalized_value`` column is written for successful fields only,
        so a failed or skipped run never clobbers a previously stored canonical
        form.

        Args:
            application_id: Id of the application to normalize.

        Returns:
            The normalization outcome with per-field results and a summary.

        Raises:
            ApplicationNotFound: When the application does not exist.
            NoExtractedFields: When document analysis has not run yet.
        """
        self._get_application(application_id)
        if not list(self._analysis_results.get_by_application(application_id)):
            raise NoExtractedFields()
        # Analysis has run at this point, so an empty field list here means it
        # genuinely extracted nothing (e.g. every document's OCR text missed
        # every pattern) rather than never having run at all. That is a real,
        # reportable outcome -- normalizing zero fields and letting the
        # pipeline continue to rule_validation lets the report honestly show
        # the missing-field failures, instead of the whole application
        # getting stuck retrying a stage that can never succeed on its own.
        fields = list(self._fields.get_by_application(application_id))
        context = self._build_context(application_id)

        items: list[NormalizedFieldItem] = []
        summary = NormalizationSummary()
        try:
            for field in fields:
                # Falls back to the same "unknown" sentinel _build_context already
                # uses for a document with no matching filename, rather than
                # letting one field with a stale/missing ocr_result_id crash
                # normalization for the whole application via an unguarded
                # dict-index lookup.
                document_id, file_name = context.get(field.ocr_result_id, (0, "unknown"))
                item = self.normalize_field(
                    field_name=field.field_name,
                    value=field.human_corrected_value or field.extracted_value or "",
                    document_id=document_id,
                    file_name=file_name,
                    verification_status=field.verification_status,
                )
                items.append(item)
                if item.status is NormalizationOutcome.NORMALIZED:
                    summary.normalized += 1
                    field.normalized_value = item.normalized_value
                elif item.status is NormalizationOutcome.SKIPPED:
                    summary.skipped += 1
                else:
                    summary.failed += 1
            summary.total = len(items)

            # The audit write must share the transaction with the field
            # mutations: both persist together or neither does. Deferring the
            # audit commit (commit=False) and committing once afterwards keeps
            # them atomic, so a failed audit write rolls the mutations back
            # instead of leaving an unaudited business change.
            self._audit.create(
                application_id=application_id,
                username="system",
                action=ACTION_NORMALIZED,
                details={
                    "status": NormalizationStatus.READY_FOR_BUSINESS_VALIDATION.value,
                    "version": NORMALIZATION_VERSION,
                    "summary": summary.model_dump(),
                },
                commit=False,
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        logger.info(
            "Normalization completed for application id=%s: total=%s "
            "normalized=%s skipped=%s failed=%s",
            application_id,
            summary.total,
            summary.normalized,
            summary.skipped,
            summary.failed,
        )
        return NormalizeResponse(
            application_id=application_id,
            processing_status=NormalizationStatus.READY_FOR_BUSINESS_VALIDATION,
            normalization_version=NORMALIZATION_VERSION,
            items=items,
            summary=summary,
        )

    def normalize_field(
        self,
        *,
        field_name: str,
        value: str,
        document_id: int = 0,
        file_name: str = "unknown",
        verification_status: str | None = None,
    ) -> NormalizedFieldItem:
        """Normalize a single field value without touching the database.

        Used by the per-application run and exposed as a public service method so
        a single field can be normalized independently (e.g. by future endpoints
        or the business-validation stage).

        Args:
            field_name: Machine-readable name of the field.
            value: Value to canonicalize.
            document_id: Owning document id, for reporting.
            file_name: Original filename of the source document, for reporting.
            verification_status: Verification state of the field; ``None`` skips
                the eligibility check.

        Returns:
            The per-field normalization result.
        """
        normalizer = self._registry.for_field(field_name)
        source_value = value or ""
        logger.info(
            "Normalizing field %s (document id=%s, normalizer=%s)",
            field_name,
            document_id,
            normalizer.identifier,
        )
        if not source_value.strip():
            return self._make_item(
                document_id=document_id,
                file_name=file_name,
                field_name=field_name,
                source_value=source_value,
                normalizer=normalizer.identifier,
                status=NormalizationOutcome.SKIPPED,
                reason="empty value",
            )
        if (
            verification_status is not None
            and not is_verified_for_normalization(verification_status)
        ):
            return self._make_item(
                document_id=document_id,
                file_name=file_name,
                field_name=field_name,
                source_value=source_value,
                normalizer=normalizer.identifier,
                status=NormalizationOutcome.SKIPPED,
                reason=f"not verified: {verification_status}",
            )
        try:
            normalized = normalizer.normalize(source_value)
        except ValueError as exc:
            logger.warning(
                "Normalization failed for field %s (document id=%s): %s",
                field_name,
                document_id,
                exc,
            )
            return self._make_item(
                document_id=document_id,
                file_name=file_name,
                field_name=field_name,
                source_value=source_value,
                normalizer=normalizer.identifier,
                status=NormalizationOutcome.FAILED,
                reason=str(exc),
            )
        logger.info(
            "Field %s normalized (document id=%s): %r -> %r",
            field_name,
            document_id,
            source_value,
            normalized,
        )
        return self._make_item(
            document_id=document_id,
            file_name=file_name,
            field_name=field_name,
            source_value=source_value,
            normalizer=normalizer.identifier,
            status=NormalizationOutcome.NORMALIZED,
            normalized_value=normalized,
        )

    def get_normalized_fields(self, *, application_id: int) -> list[NormalizedFieldRecord]:
        """Return every stored field of an application with its canonical value.

        Args:
            application_id: Id of the application to look up.

        Returns:
            The stored field records, ordered by document and field name.

        Raises:
            ApplicationNotFound: When the application does not exist.
            NoExtractedFields: When the application has no extracted fields.
        """
        self._get_application(application_id)
        fields = list(self._fields.get_by_application(application_id))
        if not fields:
            raise NoExtractedFields()
        context = self._build_context(application_id)
        return [
            NormalizedFieldRecord(
                document_id=context[field.ocr_result_id][0],
                file_name=context[field.ocr_result_id][1],
                field_name=field.field_name,
                extracted_value=field.extracted_value,
                normalized_value=field.normalized_value,
                verification_status=field.verification_status,
            )
            for field in fields
        ]

    # -- Internals ------------------------------------------------------------

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _build_context(self, application_id: int) -> Mapping[int, tuple[int, str]]:
        """Map every OCR result of the application to its document and filename."""
        file_names = {
            document.id: document.original_filename
            for document in self._documents.get_all_by_application(application_id)
        }
        return {
            ocr_result.id: (
                ocr_result.document_id,
                file_names.get(ocr_result.document_id, "unknown"),
            )
            for ocr_result in self._ocr_results.get_by_application(application_id)
        }

    @staticmethod
    def _make_item(
        *,
        document_id: int,
        file_name: str,
        field_name: str,
        source_value: str,
        normalizer: str,
        status: NormalizationOutcome,
        reason: str | None = None,
        normalized_value: str | None = None,
    ) -> NormalizedFieldItem:
        """Build a per-field normalization result item."""
        return NormalizedFieldItem(
            document_id=document_id,
            file_name=file_name,
            field_name=field_name,
            source_value=source_value,
            normalized_value=normalized_value,
            normalizer=normalizer,
            status=status,
            reason=reason,
        )


__all__ = ["NormalizationService"]
