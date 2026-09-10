"""Document analysis service.

Orchestrates the analysis pipeline for every document of an application: loads
the OCR text, detects the analysed document type, extracts structured fields,
validates them, runs the cross-field consistency rules, computes the
deterministic confidence score and verification status, and persists one
analysis result row per document. Per-document failures (missing OCR result,
undetermined type, extraction problems) are captured inside the response and
never abort the run.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models.document import Document
from app.database.models.document_analysis_result import DocumentAnalysisResult
from app.database.models.enums import DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_analysis_repository import DocumentAnalysisRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.document_analysis.constants import (
    ANALYSIS_VERSION,
    EXPECTED_FIELDS,
    AnalyzedDocumentType,
    VerificationStatus,
)
from app.document_analysis.exceptions import (
    ApplicationNotFound,
    DocumentAnalysisError,
    OCRResultNotFound,
)
from app.document_analysis.extractors import detect_document_type, extract_fields
from app.document_analysis.fallbacks import (
    AiFallbackMetrics,
    FieldFallback,
    fields_needing_ai,
    merge_fallback_values,
)
from app.document_analysis.rules import RulesEngine, scoring_components
from app.document_analysis.schemas import (
    AnalysisOutcome,
    AnalysisResultItem,
    AnalysisResultsResponse,
    AnalyzeDocumentsResponse,
    DocumentAnalysisItem,
)
from app.document_analysis.validators import ValidatorEngine

logger = logging.getLogger(__name__)

#: Default AI fallback provider factory. Production wiring assigns a factory
#: that returns a :class:`FieldFallback`; tests substitute a fake provider. The
#: module-level reference keeps the route layer thin (mirroring the OCR engine
#: factory pattern) while ``ai_fallback_enabled`` gates whether a provider is
#: ever consulted.
ai_fallback_factory: Callable[[], FieldFallback | None] | None = None

#: Storage-level DocumentType values that are not genuine required-document
#: checklist categories: OTHER_SUPPORTING_DOCUMENT is the catch-all bucket the
#: splitter (app/preprocessing/splitter.py) falls back to when a page matches
#: no checklist keyword, and BULK_UPLOAD is the pre-split placeholder type of
#: an application's raw upload, never a real document's type. Every other
#: DocumentType member is a genuine checklist category the splitter
#: recognised by name (e.g. TRIPARTITE_AGREEMENT) -- see
#: DocumentAnalysisService._recognized_checklist_type.
_UNCLASSIFIED_STORAGE_TYPES = frozenset(
    {DocumentType.OTHER_SUPPORTING_DOCUMENT, DocumentType.BULK_UPLOAD}
)

#: Storage-level checklist types that now have a real field-level extractor
#: (app.document_analysis.extractors._EXTRACTORS), keyed to the matching
#: AnalyzedDocumentType. A recognized checklist type not in this map still
#: falls back to _persist_recognized_unsupported_type -- this is the Phase 1
#: (docs/IMPLEMENTATION_ROADMAP.md) worklist, extended one document type at a
#: time as each gets a real extractor and real-sample validation.
#:
#: These are routed straight from the splitter's own title-anchored
#: classification (``document.document_type``) so the generic OCR keyword
#: table in :func:`detect_document_type` never sees them -- a document's own
#: field labels (e.g. an AMC's "IBAN" or "Account Number") must not be able
#: to misroute it into the unrelated generic keyword scoring.
_CHECKLIST_TYPE_MAP: dict[DocumentType, AnalyzedDocumentType] = {
    DocumentType.BILATERAL_AGREEMENT: AnalyzedDocumentType.BILATERAL_AGREEMENT,
    DocumentType.AUTHORITY_LETTER: AnalyzedDocumentType.AUTHORITY_LETTER,
    DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: (
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
    ),
    DocumentType.TRIPARTITE_AGREEMENT: AnalyzedDocumentType.TRIPARTITE_AGREEMENT,
    DocumentType.BUSINESS_REQUIREMENT_DOCUMENT: AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    DocumentType.ONE_LINK_LETTER: AnalyzedDocumentType.ONE_LINK_LETTER,
    #: Front only -- DocumentType.CNIC_BACK deliberately excluded, see
    #: AnalyzedDocumentType.CNIC_FRONT's comment in constants.py.
    DocumentType.CNIC_FRONT: AnalyzedDocumentType.CNIC_FRONT,
    DocumentType.FORMAL_REQUEST_LETTER: AnalyzedDocumentType.FORMAL_REQUEST_LETTER,
}


class DocumentAnalysisService:
    """Runs the analysis pipeline over an application's documents.

    Args:
        db: SQLAlchemy session used for all database interaction.
        fallback_factory: Optional factory producing an AI/VLM field fallback
            provider. When provided (and ``ai_fallback_enabled`` is true) the
            provider is consulted only for expected fields the rule pipeline
            left missing or invalid; when absent, AI is never called.
        metrics: Optional counter object recording AI fallback usage. Useful
            for benchmarks and tests; defaults to a private instance.
    """

    def __init__(
        self,
        db: Session,
        *,
        fallback_factory: Callable[[], FieldFallback | None] | None = None,
        metrics: AiFallbackMetrics | None = None,
    ) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._ocr_results = OCRRepository(db)
        self._analysis_results = DocumentAnalysisRepository(db)
        self._validators = ValidatorEngine()
        self._rules = RulesEngine()
        self._metrics = metrics or AiFallbackMetrics()
        if fallback_factory is not None:
            self._fallback = fallback_factory()
        elif get_settings().ai_fallback_enabled and ai_fallback_factory is not None:
            self._fallback = ai_fallback_factory()
        else:
            self._fallback = None

    @property
    def metrics(self) -> AiFallbackMetrics:
        """AI fallback usage counters of this service instance."""
        return self._metrics

    def analyze(self, *, application_id: int) -> AnalyzeDocumentsResponse:
        """Analyse every document of an application and persist the results.

        Each document's OCR text is turned into an explainable analysis result.
        Documents without an OCR result, with undeterminable types or with
        failing extraction are reported as failed; the run always completes.

        Args:
            application_id: Id of the application to analyse.

        Returns:
            The outcome of the analysis run for every document.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        application = self._get_application(application_id)
        documents = list(self._documents.get_all_by_application(application_id))
        logger.info(
            "Document analysis started for application id=%s (%s documents)",
            application.id,
            len(documents),
        )
        items: list[DocumentAnalysisItem] = []
        for document in documents:
            items.append(self._analyze_document(application.id, document))

        analyzed = sum(item.outcome is AnalysisOutcome.ANALYZED for item in items)
        failed = sum(item.outcome is AnalysisOutcome.FAILED for item in items)
        logger.info(
            "Document analysis completed for application id=%s: "
            "%s analyzed, %s failed",
            application.id,
            analyzed,
            failed,
        )
        return AnalyzeDocumentsResponse(
            application_id=application.id,
            items=items,
            total_analyzed=analyzed,
            total_failed=failed,
        )

    def get_results(self, *, application_id: int) -> AnalysisResultsResponse:
        """Return every stored analysis result for an application.

        Args:
            application_id: Id of the application.

        Returns:
            The stored analysis results, ordered by document.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        application = self._get_application(application_id)
        documents = {
            document.id: document
            for document in self._documents.get_all_by_application(application_id)
        }
        rows = self._analysis_results.get_by_application(application_id)
        items = [self._result_item(documents, row) for row in rows]
        logger.info(
            "Returned %s stored analysis results for application id=%s",
            len(items),
            application.id,
        )
        return AnalysisResultsResponse(
            application_id=application.id,
            items=items,
            total=len(items),
        )

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _analyze_document(
        self,
        application_id: int,
        document: Document,
    ) -> DocumentAnalysisItem:
        """Analyse one document and persist its analysis result.

        Args:
            application_id: Owning application id.
            document: Document to analyse.

        Returns:
            The per-document outcome, either analysed or failed.
        """
        started = time.perf_counter()
        try:
            ocr_result = self._ocr_results.get_by_document(document.id)
            if ocr_result is None:
                raise OCRResultNotFound()

            recognized_type = self._recognized_checklist_type(document.document_type)
            checklist_analyzed_type = (
                _CHECKLIST_TYPE_MAP.get(recognized_type)
                if recognized_type is not None
                else None
            )
            if recognized_type is not None and checklist_analyzed_type is not None:
                # The splitter's classification is anchored to a title match
                # in the page header (app/preprocessing/splitter.py), so it is
                # trusted ahead of the generic keyword scorer below: a real
                # checklist document's own required content (e.g. a Bilateral
                # Agreement's Section 6 "Account Number"/"IBAN" fields) can
                # otherwise score positively against detect_document_type's
                # unrelated bank-statement keyword table and be misrouted.
                logger.info(
                    "Document id=%s recognized as %s by its storage-level "
                    "classification; running its checklist-type extractor "
                    "(application id=%s)",
                    document.id,
                    recognized_type.value,
                    application_id,
                )
                document_type = checklist_analyzed_type
            else:
                document_type = detect_document_type(ocr_result.raw_ocr_text)
                if document_type is AnalyzedDocumentType.UNKNOWN:
                    if recognized_type is not None:
                        logger.info(
                            "Document id=%s recognized as %s by its storage-level "
                            "classification but has no field-level extractor "
                            "(application id=%s)",
                            document.id,
                            recognized_type.value,
                            application_id,
                        )
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        return self._persist_recognized_unsupported_type(
                            application_id, document, recognized_type, elapsed_ms
                        )
                    logger.warning(
                        "Document type undetermined for document id=%s (application id=%s)",
                        document.id,
                        application_id,
                    )
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    return self._persist_undetermined_type(application_id, document, elapsed_ms)

            fields = extract_fields(ocr_result.raw_ocr_text, document_type)
            validations = self._validators.run(document_type, fields)
            fields, validations = self._resolve_low_confidence_fields(
                document_type,
                text=ocr_result.raw_ocr_text,
                fields=fields,
                validations=validations,
            )
            consistency = self._rules.run(document_type, fields)
            (
                field_coverage,
                validation_rate,
                consistency_rate,
                score,
                status,
            ) = scoring_components(
                document_type,
                fields=fields,
                validation_results=validations,
                consistency_results=consistency,
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            self._analysis_results.upsert(
                application_id=application_id,
                document_id=document.id,
                document_type=document_type.value,
                extracted_fields=fields,
                validation_results=validations,
                consistency_results=consistency,
                confidence_score=score,
                verification_status=status.value,
                analysis_version=ANALYSIS_VERSION,
                processing_time_ms=elapsed_ms,
            )
            logger.info(
                "Analysis persisted for document id=%s (application id=%s): "
                "type=%s score=%.3f status=%s in %s ms "
                "(coverage=%.3f validation=%.3f consistency=%.3f)",
                document.id,
                application_id,
                document_type.value,
                score,
                status.value,
                elapsed_ms,
                field_coverage,
                validation_rate,
                consistency_rate,
            )
            invalid_count = sum(
                1 for result in validations if result["status"] == "invalid"
            )
            missing_count = sum(
                1 for result in validations if result["status"] == "missing"
            )
            if invalid_count or missing_count:
                logger.warning(
                    "Analysis of document id=%s reported %s invalid and %s missing "
                    "fields (application id=%s)",
                    document.id,
                    invalid_count,
                    missing_count,
                    application_id,
                )
            return DocumentAnalysisItem(
                document_id=document.id,
                file_name=document.original_filename,
                document_type=document_type.value,
                outcome=AnalysisOutcome.ANALYZED,
                verification_status=status.value,
                confidence_score=score,
                extracted_fields=fields,
                validation_results=validations,
                consistency_results=consistency,
                issues=self._issues(validations, consistency),
                processing_time_ms=elapsed_ms,
            )
        except DocumentAnalysisError as exc:
            logger.error(
                "Analysis failed for document id=%s (application id=%s): %s",
                document.id,
                application_id,
                exc.detail,
            )
            return self._fail_item(document, exc.detail)
        except Exception as exc:  # pragma: no cover - defensive isolation
            logger.exception(
                "Analysis failed unexpectedly for document id=%s (application id=%s)",
                document.id,
                application_id,
            )
            return self._fail_item(document, f"Unexpected analysis error: {exc}")

    def _resolve_low_confidence_fields(
        self,
        document_type: AnalyzedDocumentType,
        *,
        text: str,
        fields: dict[str, Any],
        validations: list[dict[str, str]],
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        """Consult the AI fallback for missing/invalid expected fields only.

        The rule pipeline runs first and its results are kept. When a fallback
        provider is configured (``ai_fallback_enabled`` and a factory), the
        provider is invoked once per document with just the names of the fields
        the rules left missing or invalid; resolved values are merged back and
        the affected validations are recomputed so scoring reflects the merged
        fields. With no provider configured the fields pass through untouched
        and no AI call is ever made.

        Args:
            document_type: Analysed document type.
            text: Raw document text (context for the provider).
            fields: Rule-extracted fields.
            validations: Per-field validation outcomes.

        Returns:
            The (possibly merged) fields and their recomputed validations.
        """
        needing = fields_needing_ai(
            fields,
            validations,
            EXPECTED_FIELDS.get(document_type, frozenset()),
        )
        self._metrics.fields_requiring_ai += len(needing)
        if not needing or self._fallback is None:
            return fields, validations

        self._metrics.ai_calls += 1
        self._metrics.fields_requested += len(needing)
        try:
            resolved = self._fallback.resolve(
                document_type=document_type,
                text=text,
                fields=fields,
                field_names=needing,
            )
        except Exception as exc:  # defensive isolation: AI must never break analysis
            self._metrics.failed_calls += 1
            logger.warning(
                "AI fallback failed for document type=%s fields=%s: %s",
                document_type.value,
                needing,
                exc,
            )
            return fields, validations

        merged = merge_fallback_values(fields, resolved or {}, needing)
        # Count fields the provider actually resolved: ones it added or whose
        # value it changed (an invalid-but-present field corrected by AI).
        resolved_names = sorted(
            name
            for name in needing
            if name in merged
            and (name not in fields or fields[name] != merged[name])
        )
        self._metrics.fields_resolved += len(resolved_names)
        if not resolved_names:
            return fields, validations
        logger.info(
            "AI fallback resolved %s field(s) for document type=%s: %s",
            len(resolved_names),
            document_type.value,
            resolved_names,
        )
        return merged, self._validators.run(document_type, merged)

    @staticmethod
    def _recognized_checklist_type(storage_type: DocumentType | None) -> DocumentType | None:
        """Return the document's real checklist type, or ``None`` if it has none.

        ``document.document_type`` is set by the splitter
        (``app/preprocessing/splitter.py``) from the real required-document
        checklist vocabulary (e.g. ``TRIPARTITE_AGREEMENT``) -- a completely
        different, non-overlapping vocabulary from the 4-category keyword
        table :func:`detect_document_type` matches against (bank statement,
        payslip, ID document, tax document). When keyword detection reports
        ``UNKNOWN``, this checks whether the splitter already knows the real
        type, so that type can be stored honestly instead of a generic
        "undetermined" -- without pretending an extractor ran for it. By the
        time this is reached (keyword detection already reported ``UNKNOWN``),
        every checklist category with a real extractor has already been routed
        away by ``_analyze_document``'s checklist-type branch, so this only
        ever persists the recognised-but-not-yet-extracted categories.

        Returns ``None`` for ``OTHER_SUPPORTING_DOCUMENT`` (the splitter's own
        catch-all for a page matching no checklist keyword) and
        ``BULK_UPLOAD`` (the pre-split placeholder type): neither is a real
        classification, so a document with either type is genuinely
        undetermined, same as before this method existed.
        """
        if storage_type is None or storage_type in _UNCLASSIFIED_STORAGE_TYPES:
            return None
        return storage_type

    def _persist_undetermined_type(
        self,
        application_id: int,
        document: Document,
        elapsed_ms: int,
    ) -> DocumentAnalysisItem:
        """Persist an analysis result for a document whose type couldn't be determined.

        Reached only when neither classifier has an answer: the OCR-keyword
        table in :func:`detect_document_type` scored no match, and the
        splitter's own classification (``document.document_type``) is itself
        a placeholder (``OTHER_SUPPORTING_DOCUMENT`` or ``BULK_UPLOAD``), not
        a real checklist category -- see :meth:`_recognized_checklist_type`
        for the case where the splitter does know the real type. This is not
        an analysis failure -- it genuinely has no matching extractor -- so
        this stores a result row (``NEEDS_REVIEW``, no extracted fields)
        instead of raising, ensuring the document stays visible to human
        review and downstream reporting rather than silently vanishing from
        ``document_analysis_results``.

        Deliberately bypasses :func:`scoring_components`: with no expected
        fields and nothing to validate, its rate calculations default to
        vacuously-true 1.0s, which would misreport this document as fully
        verified instead of undetermined.

        Args:
            application_id: Owning application id.
            document: Document whose type could not be determined.
            elapsed_ms: Time spent up to the point of detection.

        Returns:
            The persisted, analysed (not failed) outcome.
        """
        message = "Document type could not be determined from the extracted text"
        self._analysis_results.upsert(
            application_id=application_id,
            document_id=document.id,
            document_type=AnalyzedDocumentType.UNKNOWN.value,
            extracted_fields={},
            validation_results=[],
            consistency_results=[],
            confidence_score=None,
            verification_status=VerificationStatus.NEEDS_REVIEW.value,
            analysis_version=ANALYSIS_VERSION,
            processing_time_ms=elapsed_ms,
        )
        return DocumentAnalysisItem(
            document_id=document.id,
            file_name=document.original_filename,
            document_type=AnalyzedDocumentType.UNKNOWN.value,
            outcome=AnalysisOutcome.ANALYZED,
            verification_status=VerificationStatus.NEEDS_REVIEW.value,
            confidence_score=None,
            extracted_fields={},
            validation_results=[],
            consistency_results=[],
            issues=[],
            processing_time_ms=elapsed_ms,
            message=message,
        )

    def _persist_recognized_unsupported_type(
        self,
        application_id: int,
        document: Document,
        document_type: DocumentType,
        elapsed_ms: int,
    ) -> DocumentAnalysisItem:
        """Persist an analysis result for a document of a known checklist type
        that has no field-level extractor.

        Stores the splitter's real type (e.g. ``TRIPARTITE_AGREEMENT``)
        instead of ``AnalyzedDocumentType.UNKNOWN``, so the result is
        honestly labelled and distinguishable from a genuinely unclassifiable
        document. Fields, validations and consistency results stay empty and
        confidence stays unset -- same as :meth:`_persist_undetermined_type`
        -- because no ``RegexExtractor`` exists for any checklist category
        yet; this method only fixes the *label*, it does not fabricate
        extraction that didn't happen.

        Args:
            application_id: Owning application id.
            document: Document being analysed.
            document_type: The splitter's real checklist type for this document.
            elapsed_ms: Time spent up to the point of detection.

        Returns:
            The persisted, analysed (not failed) outcome.
        """
        message = (
            f"Document recognized as {document_type.value}, but field-level "
            "analysis is not yet supported for this document type"
        )
        self._analysis_results.upsert(
            application_id=application_id,
            document_id=document.id,
            document_type=document_type.value,
            extracted_fields={},
            validation_results=[],
            consistency_results=[],
            confidence_score=None,
            verification_status=VerificationStatus.NEEDS_REVIEW.value,
            analysis_version=ANALYSIS_VERSION,
            processing_time_ms=elapsed_ms,
        )
        return DocumentAnalysisItem(
            document_id=document.id,
            file_name=document.original_filename,
            document_type=document_type.value,
            outcome=AnalysisOutcome.ANALYZED,
            verification_status=VerificationStatus.NEEDS_REVIEW.value,
            confidence_score=None,
            extracted_fields={},
            validation_results=[],
            consistency_results=[],
            issues=[],
            processing_time_ms=elapsed_ms,
            message=message,
        )

    def _fail_item(self, document: Document, message: str) -> DocumentAnalysisItem:
        """Build a failed outcome for a document."""
        return DocumentAnalysisItem(
            document_id=document.id,
            file_name=document.original_filename,
            outcome=AnalysisOutcome.FAILED,
            message=message,
        )

    def _result_item(
        self,
        documents: dict[int, Document],
        row: DocumentAnalysisResult,
    ) -> AnalysisResultItem:
        """Map a stored analysis row onto its response schema.

        Args:
            documents: Application documents keyed by id.
            row: Stored analysis result.

        Returns:
            The serialized result item.
        """
        document = documents.get(row.document_id)
        validations = row.validation_results or []
        consistency = row.consistency_results or []
        return AnalysisResultItem(
            document_id=row.document_id,
            file_name=document.original_filename if document else "unknown",
            document_type=row.document_type,
            verification_status=row.verification_status,
            confidence_score=row.confidence_score,
            extracted_fields=row.extracted_fields,
            validation_results=validations,
            consistency_results=consistency,
            issues=self._issues(validations, consistency),
            processing_time_ms=row.processing_time_ms,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _issues(
        validations: list[dict],
        consistency: list[dict],
    ) -> list[str]:
        """Collect every non-passing validation and consistency message."""
        issues = [v["message"] for v in validations if v.get("status") != "valid"]
        issues += [c["message"] for c in consistency if c.get("status") != "pass"]
        return issues
