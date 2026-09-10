"""Document processing service.

Orchestrates the extraction pipeline for every document of an application:
enforces the technical validation gate, routes each document to the right
extractor, persists one OCR result row per document (reusing the Phase 2 OCR
results table) and reads stored results back. Per-document failures are captured
inside the response and never abort the run.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models.document import Document
from app.database.models.enums import (
    ApplicationStatus,
    DocumentProcessingStatus,
    DocumentType,
    ValidationStatus,
)
from app.database.models.ocr_result import OCRResult
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.document_processing.constants import (
    MIN_PROCESSING_TIMEOUT_SECONDS,
    PROCESSING_TIMEOUT_SECONDS_PER_PAGE,
    DocumentSource,
)
from app.document_processing.exceptions import (
    ApplicationNotFound,
    DocumentProcessingError,
    TechnicalValidationRequired,
)
from app.document_processing.processors import (
    DigitalPdfExtractor,
    ExtractionResult,
    ImageExtractor,
    OCREngine,
    ScannedPdfExtractor,
    _create_ocr_engine,
)
from app.document_processing.schemas import (
    DocumentProcessingResult,
    OcrResultItem,
    OcrResultsResponse,
    ProcessDocumentsResponse,
    ProcessingOutcome,
)
from app.document_processing.validators import (
    assert_non_empty_text,
    classify_document_source,
    detect_format,
    resolve_document_file,
)
from app.technical_validation.services import TechnicalValidationService
from app.upload.storage import StorageService

logger = logging.getLogger(__name__)

#: Default OCR engine factory. Tests swap this module-level reference for a fake
#: engine so the pipeline runs without downloading OCR models.
ocr_engine_factory: Callable[[], OCREngine] = _create_ocr_engine


class DocumentProcessingService:
    """Routes and executes text extraction for an application's documents.

    Args:
        db: SQLAlchemy session used for all database interaction.
        engine_factory: Optional factory producing the OCR engine used for
            scanned sources. Defaults to :data:`ocr_engine_factory`.
    """

    def __init__(
        self,
        db: Session,
        *,
        engine_factory: Callable[[], OCREngine] | None = None,
    ) -> None:
        self._db = db
        self._storage = StorageService(get_settings().upload_storage_root)
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._ocr_results = OCRRepository(db)
        self._technical = TechnicalValidationService(db)
        self._engine_factory = engine_factory or ocr_engine_factory

    def process(self, *, application_id: int) -> ProcessDocumentsResponse:
        """Run the extraction pipeline over every document of an application.

        Documents that did not pass Phase 5 technical validation are skipped,
        never processed. Each processed document's raw text and metrics are
        persisted as its OCR result; per-document failures are captured in the
        response with the document's processing status set to ``FAILED``.

        Args:
            application_id: Id of the application to process.

        Returns:
            The outcome of the run for every document.

        Raises:
            ApplicationNotFound: When the application does not exist.
            TechnicalValidationRequired: When the application has documents but
                no stored technical validation reports.
        """
        application = self._get_application(application_id)
        documents = list(
            self._documents.get_all_by_application(application_id)
        )
        reports = self._technical.get_reports(application_id=application_id)
        if documents and not reports.items:
            raise TechnicalValidationRequired()
        statuses = {
            report.document_id: report.validation_status for report in reports.items
        }
        logger.info(
            "Document processing started for application id=%s (%s documents)",
            application.id,
            len(documents),
        )
        items: list[DocumentProcessingResult] = []
        for document in documents:
            status = statuses.get(document.id)
            if status is not ValidationStatus.PASS:
                logger.warning(
                    "Skipping document id=%s (application id=%s): "
                    "did not pass technical validation",
                    document.id,
                    application.id,
                )
                items.append(
                    self._skipped_result(
                        document,
                        "Document did not pass technical validation",
                    )
                )
                continue
            items.append(self._process_document(application.id, document))

        processed = sum(item.outcome is ProcessingOutcome.PROCESSED for item in items)
        skipped = sum(item.outcome is ProcessingOutcome.SKIPPED for item in items)
        failed = sum(item.outcome is ProcessingOutcome.FAILED for item in items)
        logger.info(
            "Document processing completed for application id=%s: "
            "%s processed, %s skipped, %s failed",
            application.id,
            processed,
            skipped,
            failed,
        )
        return ProcessDocumentsResponse(
            application_id=application.id,
            items=items,
            total_processed=processed,
            total_skipped=skipped,
            total_failed=failed,
        )

    def get_results(self, *, application_id: int) -> OcrResultsResponse:
        """Return every stored OCR/text extraction result for an application.

        Args:
            application_id: Id of the application.

        Returns:
            The stored extraction results, ordered by document.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        application = self._get_application(application_id)
        documents = {
            document.id: document
            for document in self._documents.get_all_by_application(application_id)
        }
        rows = self._ocr_results.get_by_application(application_id)
        items = [self._result_item(documents, row) for row in rows]
        logger.info(
            "Returned %s stored OCR results for application id=%s",
            len(items),
            application.id,
        )
        return OcrResultsResponse(
            application_id=application.id,
            items=items,
            total=len(items),
        )

    def process_one(
        self,
        *,
        application_id: int,
        document_id: int,
    ) -> DocumentProcessingResult:
        """Run the existing extraction pipeline for one technically valid document.

        Queue workers use this method to preserve the same routing hierarchy as
        the application-wide endpoint: digital text first, OCR only when needed,
        and AI/VLM fallbacks only where the existing pipeline elects to use them.
        """
        self._get_application(application_id)
        document = self._documents.get_by_id(document_id)
        if document is None or document.application_id != application_id:
            raise DocumentProcessingError("Document not found")
        if document.document_type == DocumentType.BULK_UPLOAD:
            return self._process_bulk_upload(application_id, document)
            
        reports = self._technical.get_reports(application_id=application_id)
        statuses = {
            report.document_id: report.validation_status for report in reports.items
        }
        if statuses.get(document.id) is not ValidationStatus.PASS:
            return self._skipped_result(
                document,
                "Document did not pass technical validation",
            )
        return self._process_document(application_id, document)

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _flag_for_manual_review(self, application_id: int, message: str) -> None:
        """Best-effort, additive note that an application needs manual review.

        No dedicated review-flag column/status exists on ``main`` yet, so
        this appends an operator-visible note rather than introducing a new
        migration -- mirrors ``UploadService._flag_for_manual_review``.
        """
        application = self._applications.get_by_id(application_id)
        if application is None:
            return
        stamped = f"[SYSTEM] {message}"
        application.notes = (
            f"{application.notes}\n{stamped}" if application.notes else stamped
        )

    def _process_bulk_upload(self, application_id: int, document: Document) -> DocumentProcessingResult:
        from app.database.repositories.queue_job_repository import QueueJobRepository
        from app.preprocessing.splitter import DocumentSplitter
        from app.technical_validation.services import TechnicalValidationService
        from app.upload.constants import MAX_COPIES_BY_DOCUMENT_TYPE
        
        self._documents.update_status(document, DocumentProcessingStatus.PROCESSING)
        
        try:
            path = resolve_document_file(self._storage, document.stored_file_path)
            with open(path, "rb") as f:
                content = f.read()

            split_result = DocumentSplitter.split_bulk_pdf(
                content,
                max_bytes=get_settings().max_upload_size_mb * 1024 * 1024,
                ocr_engine=self._engine_factory()
            )
            split_results = split_result.documents

            batch_counts: dict[DocumentType, int] = {}
            for doc_type, _ in split_results:
                batch_counts[doc_type] = batch_counts.get(doc_type, 0) + 1

            statement = (
                select(Document.document_type, func.max(Document.copy_number))
                .where(Document.application_id == application_id)
                .group_by(Document.document_type)
            )
            existing_max = {
                document_type: int(max_copy or 0)
                for document_type, max_copy in self._db.execute(statement)
            }

            for doc_type, count in batch_counts.items():
                max_copies = MAX_COPIES_BY_DOCUMENT_TYPE.get(doc_type, 1)
                total = existing_max.get(doc_type, 0) + count
                if total > max_copies:
                    # No longer a hard rejection (department decision,
                    # 2026-08-19, see CONTEXT.md): a real bulk file can
                    # legitimately split into more copies of a type than the
                    # configured threshold when the splitter mis-slices
                    # unrelated content into that type's boundary (see the
                    # GDA Abbotabad findings) -- rejecting the whole upload
                    # over a count doesn't fix that document-boundary
                    # problem, it just blocks the operator from ever seeing
                    # the file. Accept it and flag for manual review instead.
                    logger.warning(
                        "Application id=%s: bulk split produced %s copies of "
                        "%s, exceeding the configured threshold of %s -- "
                        "accepting and flagging for manual review instead of "
                        "rejecting.",
                        application_id,
                        total,
                        doc_type.value,
                        max_copies,
                    )
                    self._flag_for_manual_review(
                        application_id,
                        f"{doc_type.value} split into {total} copies, exceeding "
                        f"the configured threshold of {max_copies}. Flagged for "
                        f"manual review.",
                    )

            next_copy = {doc_type: existing_max.get(doc_type, 0) + 1 for doc_type in batch_counts}
            created_documents: list[Document] = []
            
            for doc_type, pdf_bytes in split_results:
                copy_number = next_copy[doc_type]
                next_copy[doc_type] += 1
                stored_path = self._storage.save(application_id, doc_type, pdf_bytes, ".pdf")
                created_documents.append(
                    Document(
                        application_id=application_id,
                        document_type=doc_type,
                        copy_number=copy_number,
                        original_filename=f"{doc_type.value.lower()}_copy{copy_number}.pdf",
                        stored_file_path=stored_path,
                        file_type="application/pdf",
                        processing_status=DocumentProcessingStatus.UPLOADED,
                    )
                )

            self._documents.create_many(documents=created_documents)

            if split_result.warnings:
                # Surfaces the splitter's absorption-disagreement signal
                # (app/preprocessing/splitter.py::AbsorptionWarning, logged
                # since c236ba2 but never visible to a human) the same way
                # the too-many-copies case above already is: an
                # operator-visible note on the application, not a silent
                # console-only log line. Grouped per affected document so
                # one blob with several absorbed pages produces one note,
                # not one line per page.
                warnings_by_document: dict[int, list[str]] = {}
                for warning in split_result.warnings:
                    warnings_by_document.setdefault(warning.document_index, []).append(
                        f"page {warning.page_number + 1} weakly matches "
                        f"{warning.weakly_matched_type.value}"
                    )
                for document_index, page_notes in warnings_by_document.items():
                    flagged_document = created_documents[document_index]
                    self._flag_for_manual_review(
                        application_id,
                        f"{flagged_document.document_type.value} "
                        f"(copy {flagged_document.copy_number}) may contain merged "
                        f"content from another document: {'; '.join(page_notes)}. "
                        f"Flagged for manual review.",
                    )

            TechnicalValidationService(self._db).validate(application_id=application_id)

            # ---- Completeness gate -------------------------------------------------
            # After splitting the bulk PDF the document set may be incomplete.
            # An incomplete application must NOT enter active processing: the
            # operator needs to review the missing documents and either request
            # them or wait for a resubmission before processing starts.
            from app.completeness.constants import CompletenessStatus
            from app.completeness.services import CompletenessService

            completeness = CompletenessService(self._db).verify(
                application_id=application_id,
            )
            application = self._applications.get_by_id(application_id)

            if completeness.status is not CompletenessStatus.COMPLETE:
                # Transition to NEEDS_DOCUMENTS so the operator can act.
                if application is not None and application.status is not ApplicationStatus.NEEDS_DOCUMENTS:
                    self._applications.update(
                        application, status=ApplicationStatus.NEEDS_DOCUMENTS,
                    )
                    logger.info(
                        "Bulk split for application id=%s produced %s/%s "
                        "required documents (incomplete) -> NEEDS_DOCUMENTS",
                        application_id,
                        sum(1 for d in completeness.required_documents if d.is_present),
                        len(completeness.required_documents),
                    )
                self._documents.update_status(document, DocumentProcessingStatus.COMPLETED)
                return DocumentProcessingResult(
                    document_id=document.id,
                    file_name=document.original_filename,
                    outcome=ProcessingOutcome.PROCESSED,
                    processing_method=None,
                    raw_text=None,
                )

            # Application is complete -- enqueue individual documents for
            # OCR processing and transition to PROCESSING.
            QueueJobRepository(self._db).enqueue_uploaded_documents(
                application_id=application_id,
                max_attempts=get_settings().bulk_queue_max_attempts,
            )
            if application is not None and application.status is not ApplicationStatus.PROCESSING:
                self._applications.update(
                    application, status=ApplicationStatus.PROCESSING,
                )

            self._documents.update_status(document, DocumentProcessingStatus.COMPLETED)
            logger.info("Successfully split bulk upload id=%s into %s documents (complete)", document.id, len(created_documents))

            return DocumentProcessingResult(
                document_id=document.id,
                file_name=document.original_filename,
                outcome=ProcessingOutcome.PROCESSED,
                processing_method=None,
                raw_text=None,
            )
        except Exception as exc:
            logger.exception("Bulk split failed for document id=%s", document.id)
            return self._fail_document(document, str(exc))

    def _process_document(
        self,
        application_id: int,
        document: Document,
    ) -> DocumentProcessingResult:
        """Extract text from one document and persist the OCR result.

        Args:
            application_id: Owning application id.
            document: Document to process.

        Returns:
            The per-document outcome, either processed or failed.
        """
        self._documents.update_status(
            document,
            DocumentProcessingStatus.PROCESSING,
        )
        started = time.perf_counter()
        try:
            result = self._extract(document)
            assert_non_empty_text(result.text)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._ocr_results.upsert(
                document_id=document.id,
                raw_ocr_text=result.text,
                ocr_engine=result.ocr_engine,
                processing_time_ms=elapsed_ms,
                overall_confidence=result.overall_confidence,
                processing_method=result.processing_method.value,
                page_count=result.page_count,
                character_count=result.character_count,
                processed_at=datetime.now(UTC),
            )
            self._documents.update_status(
                document,
                DocumentProcessingStatus.COMPLETED,
            )
            logger.info(
                "Text extraction completed for document id=%s (application id=%s): "
                "%s characters via %s in %s ms",
                document.id,
                application_id,
                result.character_count,
                result.processing_method.value,
                elapsed_ms,
            )
            return DocumentProcessingResult(
                document_id=document.id,
                file_name=document.original_filename,
                outcome=ProcessingOutcome.PROCESSED,
                processing_method=result.processing_method,
                ocr_engine=result.ocr_engine,
                page_count=result.page_count,
                character_count=result.character_count,
                processing_time_ms=elapsed_ms,
                overall_confidence=result.overall_confidence,
                raw_text=result.text,
            )
        except DocumentProcessingError as exc:
            return self._fail_document(document, exc.detail)
        except Exception as exc:  # pragma: no cover - defensive isolation
            logger.exception(
                "Processing failed unexpectedly for document id=%s",
                document.id,
            )
            return self._fail_document(document, f"Unexpected processing error: {exc}")

    def _extract(self, document: Document) -> ExtractionResult:
        """Resolve, route and extract text from one document.

        Args:
            document: Document whose stored file is processed.

        Returns:
            The extraction result with text and metrics.

        Raises:
            DocumentProcessingError: When the file, format or engine fails.
        """
        path = resolve_document_file(self._storage, document.stored_file_path)
        file_format = detect_format(document.stored_file_path)
        decision = classify_document_source(path, file_format)
        logger.info(
            "Document routing decision for document id=%s: source=%s",
            document.id,
            decision.source.value,
        )
        if decision.source is DocumentSource.DIGITAL_PDF:
            extractor = DigitalPdfExtractor(decision.probed_text, decision.page_count or 0)
        elif decision.source is DocumentSource.SCANNED_PDF:
            # Sized from the real page count (only known now, post-routing) so
            # the budget scales with the document instead of a flat guess.
            budget = max(
                (decision.page_count or 1) * PROCESSING_TIMEOUT_SECONDS_PER_PAGE,
                MIN_PROCESSING_TIMEOUT_SECONDS,
            )
            extractor = ScannedPdfExtractor(
                self._engine_factory(),
                path,
                deadline=time.monotonic() + budget,
            )
        else:
            extractor = ImageExtractor(self._engine_factory(), path)
        return extractor.extract()

    def _fail_document(self, document: Document, message: str) -> DocumentProcessingResult:
        """Mark a document as failed and return its failed outcome."""
        self._documents.update_status(document, DocumentProcessingStatus.FAILED)
        logger.error(
            "Processing failed for document id=%s: %s",
            document.id,
            message,
        )
        return DocumentProcessingResult(
            document_id=document.id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.FAILED,
            message=message,
        )

    def _skipped_result(self, document: Document, message: str) -> DocumentProcessingResult:
        """Build a skipped outcome without touching the document's status."""
        return DocumentProcessingResult(
            document_id=document.id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.SKIPPED,
            message=message,
        )

    def _result_item(self, documents: dict[int, Document], row: OCRResult) -> OcrResultItem:
        """Map a stored OCR result row onto its response schema.

        Args:
            documents: Application documents keyed by id.
            row: Stored OCR result.

        Returns:
            The serialized result item.
        """
        document = documents.get(row.document_id)
        return OcrResultItem(
            document_id=row.document_id,
            file_name=document.original_filename if document else "unknown",
            raw_ocr_text=row.raw_ocr_text,
            ocr_engine=row.ocr_engine,
            processing_method=row.processing_method,
            processing_time_ms=row.processing_time_ms,
            overall_confidence=row.overall_confidence,
            page_count=row.page_count,
            character_count=row.character_count,
            processed_at=row.processed_at,
        )
