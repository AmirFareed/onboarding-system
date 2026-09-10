"""Confidence scoring and human verification service.

Computes a field-level confidence for every extracted field of an application's
analyzed documents, decides whether human review is required (any critical
field below the configured threshold), returns only the low-confidence fields
for review, applies the employee's decisions and recomputes the final status.
The scoring math lives in module-level pure functions so it can be unit-tested
without a database; the service orchestrates them and persists the outcome.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.confidence.constants import (
    ACTION_CANNOT_VERIFY,
    ACTION_CORRECTED,
    ACTION_EVALUATED,
    ACTION_HALTED,
    ACTION_REVIEWED,
    ACTION_VERIFIED,
    CONFIDENCE_VERSION,
    LOW_OCR_CONFIDENCE,
    REASON_LOW_OCR,
    REASON_MISSING_CONTEXT,
    REASON_REGEX_MISMATCH,
    REASON_TEMPLATE_MISMATCH,
    REASON_VALID,
    REGEX_SCORE_INVALID,
    REGEX_SCORE_MISSING,
    REGEX_SCORE_VALID,
    SOURCE_AI,
    SOURCE_OCR,
    SOURCE_REGEX,
    SOURCE_TEMPLATE,
    TEMPLATE_MISMATCH_COVERAGE,
    EvaluationStatus,
    FieldVerificationStatus,
    is_critical,
)
from app.confidence.exceptions import (
    ApplicationNotFound,
    NoAnalysisResults,
    ReviewAlreadyApplied,
    ReviewNotRequired,
)
from app.confidence.schemas import (
    EvaluateResponse,
    FieldConfidenceResult,
    ReviewDecisionType,
    ReviewRequest,
    ReviewResponse,
)
from app.confidence.validators import validate_review_request
from app.core.config import get_settings
from app.database.models.extracted_field import ExtractedField
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.document_analysis_repository import DocumentAnalysisRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.extracted_field_repository import ExtractedFieldRepository
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.document_analysis.constants import EXPECTED_FIELDS
from app.feedback.constants import ORIGIN_LOW_CONFIDENCE_REVIEW

logger = logging.getLogger(__name__)

#: Deterministic preference order used to break ties between confidence sources.
_SOURCE_PRIORITY: dict[str, int] = {
    SOURCE_REGEX: 0,
    SOURCE_TEMPLATE: 1,
    SOURCE_OCR: 2,
    SOURCE_AI: 3,
}


def find_validation_status(
    validation_results: list[dict[str, Any]],
    field_name: str,
) -> str | None:
    """Return the validation status (``valid``/``invalid``/``missing``) of a field.

    Args:
        validation_results: Per-field validation outcomes of a document.
        field_name: Name of the field to look up.

    Returns:
        The field's validation status, or ``None`` when no validation ran for it.
    """
    for result in validation_results:
        if result.get("field") == field_name:
            return result.get("status")
    return None


def regex_source_confidence(validation_status: str | None) -> float:
    """Map a field's validation status onto a regex source confidence.

    A field that validated is trustworthy; a field whose value matched a
    pattern but failed validation is not; a missing field scores zero. Fields
    without a validation entry still matched their extraction pattern, so they
    are treated as valid.

    Args:
        validation_status: Status of the field validation, if any.

    Returns:
        The regex confidence (0.0 - 1.0).
    """
    if validation_status == "invalid":
        return REGEX_SCORE_INVALID
    if validation_status == "missing":
        return REGEX_SCORE_MISSING
    return REGEX_SCORE_VALID


def template_coverage(expected_fields: set[str], present_fields: set[str]) -> float:
    """Return the fraction of expected fields a document carried.

    The coverage expresses how well the document matched its template: a low
    value means expected context is missing and every extracted field is less
    trustworthy.

    Args:
        expected_fields: Fields the document's type is expected to carry.
        present_fields: Fields actually extracted from the document.

    Returns:
        The coverage fraction (0.0 - 1.0), or 1.0 when nothing is expected.
    """
    if not expected_fields:
        return 1.0
    return len(present_fields & expected_fields) / len(expected_fields)


def compute_field_confidence(
    weights: dict[str, float],
    sources: dict[str, float | None],
) -> tuple[float, str | None]:
    """Blend the available confidence sources into a single field confidence.

    Only sources that both have a configured weight above zero and produced a
    value contribute. The contributing weights are renormalized so a missing
    source never drags the score down; the result is clamped to ``[0.0, 1.0]``.
    The returned source is the dominant contributor (ties resolved by a
    deterministic preference order).

    Args:
        weights: Configured source weights (``regex``, ``template``, ``ocr``,
            ``ai``).
        sources: Confidence value per source; ``None`` marks a source that did
            not contribute (e.g. OCR for a digital PDF, or AI fallback that is
            not yet available).

    Returns:
        A tuple of the blended confidence and the dominant source identifier.
    """
    available = {
        name: value
        for name, value in sources.items()
        if value is not None and weights.get(name, 0.0) > 0.0
    }
    if not available:
        return 0.0, None
    total = sum(weights[name] for name in available)
    score = sum(weights[name] * available[name] for name in available) / total
    primary = max(
        available,
        key=lambda name: (
            weights[name] * available[name],
            -_SOURCE_PRIORITY.get(name, len(_SOURCE_PRIORITY)),
        ),
    )
    return max(0.0, min(1.0, score)), primary


def build_confidence_reason(
    validation_status: str | None,
    ocr_confidence: float | None,
    coverage: float,
) -> str:
    """Explain a field's confidence with the reasons that applied.

    Args:
        validation_status: Status of the field validation, if any.
        ocr_confidence: Document-level OCR confidence, if OCR ran.
        coverage: Template coverage of the field's document.

    Returns:
        A human-readable reason string.
    """
    fragments: list[str] = []
    if validation_status == "invalid":
        fragments.append(REASON_REGEX_MISMATCH)
    elif validation_status == "missing":
        fragments.append(REASON_MISSING_CONTEXT)
    if ocr_confidence is not None and ocr_confidence < LOW_OCR_CONFIDENCE:
        fragments.append(REASON_LOW_OCR)
    if coverage < TEMPLATE_MISMATCH_COVERAGE:
        fragments.append(REASON_TEMPLATE_MISMATCH)
    return "; ".join(fragments) if fragments else REASON_VALID


def decide_processing_status(
    entries: list[dict[str, Any]],
    threshold: float,
) -> tuple[EvaluationStatus, set[str], list[str]]:
    """Decide the application status from the per-field confidences.

    A critical field below the threshold forces human review; when only
    non-critical fields are low the application is ready for normalization. The
    low-confidence fields (critical and non-critical) are the ones returned for
    review. Boundary values at or above the threshold are considered sufficient.

    Args:
        entries: Field records carrying ``field_name``, ``score`` and
            ``resolved`` (already verified by a human).
        threshold: Confidence threshold (0.0 - 1.0).

    Returns:
        A tuple of the processing status, the names of the fields requiring
        review and the critical fields that failed.
    """
    low = [
        entry
        for entry in entries
        if not entry["resolved"] and entry["score"] < threshold
    ]
    critical_low = [
        entry for entry in low if is_critical(entry["field_name"])
    ]
    if critical_low:
        return (
            EvaluationStatus.REQUIRES_HUMAN_REVIEW,
            {entry["field_name"] for entry in low},
            sorted({entry["field_name"] for entry in critical_low}),
        )
    return EvaluationStatus.READY_FOR_NORMALIZATION, set(), []


class ConfidenceService:
    """Scores and reviews an application's extracted fields.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._analysis_results = DocumentAnalysisRepository(db)
        self._ocr_results = OCRRepository(db)
        self._fields = ExtractedFieldRepository(db)
        self._feedback = FeedbackRepository(db)
        self._audit = AuditLogRepository(db)
        self._settings = get_settings()

    # -- Public API -----------------------------------------------------------

    def evaluate(self, *, application_id: int) -> EvaluateResponse:
        """Score every extracted field of an application and decide the status.

        Each analyzed document's extracted fields are blended from the available
        confidence sources, persisted as ``extracted_fields`` rows (keyed on the
        document's OCR result and field name) and evaluated against the
        configured threshold. A critical field below the threshold returns only
        the low-confidence fields for human review.

        Args:
            application_id: Id of the application to evaluate.

        Returns:
            The evaluation outcome.

        Raises:
            ApplicationNotFound: When the application does not exist.
            NoAnalysisResults: When the application has no analyzed documents.
        """
        self._get_application(application_id)
        results = list(self._analysis_results.get_by_application(application_id))
        if not results:
            raise NoAnalysisResults()
        documents = {
            document.id: document
            for document in self._documents.get_all_by_application(application_id)
        }
        weights = self._settings.confidence_weights
        threshold = self._settings.confidence_threshold

        entries = self._collect_field_entries(results, documents, weights)
        self._mark_human_resolved(entries)
        status, flagged_names, critical_failures = decide_processing_status(
            entries, threshold
        )
        overall = self._overall_confidence(entries)

        try:
            for entry in entries:
                entry_status = (
                    entry["status"]
                    if entry["resolved"]
                    else FieldVerificationStatus.PENDING_REVIEW.value
                    if entry["field_name"] in flagged_names
                    else FieldVerificationStatus.AUTO_VERIFIED.value
                )
                entry["row"] = self._fields.upsert(
                    ocr_result_id=entry["ocr_result_id"],
                    field_name=entry["field_name"],
                    extracted_value=entry["extracted_value"],
                    confidence_score=entry["score"],
                    confidence_source=entry["primary"],
                    confidence_reason=entry["reason"],
                    verification_status=entry_status,
                    normalized_value=entry["normalized_value"],
                    commit=False,
                )

            fields_requiring_review = [
                self._to_field_result(entry)
                for entry in entries
                if entry["field_name"] in flagged_names
            ]
            # The audit write must share the transaction with the field upserts:
            # both persist together or neither does. Deferring the audit commit
            # (commit=False) and committing once afterwards keeps them atomic,
            # so a failed audit write rolls the evaluation back instead of
            # leaving an unaudited business change.
            self._audit.create(
                application_id=application_id,
                username="system",
                action=ACTION_EVALUATED,
                details={
                    "status": status.value,
                    "version": CONFIDENCE_VERSION,
                    "field_count": len(entries),
                    "flagged_fields": sorted(flagged_names),
                    "critical_failures": critical_failures,
                },
                commit=False,
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        overall_display = f"{overall:.3f}" if overall is not None else "None"
        logger.info(
            "Confidence evaluated for application id=%s: status=%s "
            "overall=%s threshold=%.3f fields=%s flagged=%s",
            application_id,
            status.value,
            overall_display,
            threshold,
            len(entries),
            sorted(flagged_names),
        )
        return EvaluateResponse(
            application_id=application_id,
            processing_status=status,
            overall_confidence=overall,
            threshold=threshold,
            fields_requiring_review=fields_requiring_review,
            critical_failures=critical_failures,
        )

    def review(
        self, *, application_id: int, request: ReviewRequest, reviewer_name: str
    ) -> ReviewResponse:
        """Apply an employee's decisions to the flagged fields.

        Verified and corrected fields become human-verified ground truth
        (confidence recalculated to 1.0); corrected fields additionally update
        the extracted value, record a feedback-dataset sample and are audited.
        A ``CANNOT_VERIFY`` decision on any flagged field halts processing.

        Args:
            application_id: Id of the application being reviewed.
            request: Review payload with the employee's decisions.
            reviewer_name: Name of the authenticated employee submitting the
                review.

        Returns:
            The final processing status.

        Raises:
            ApplicationNotFound: When the application does not exist.
            ReviewNotRequired: When no evaluation awaits review.
            ReviewAlreadyApplied: When every flagged field is already reviewed.
            InvalidReviewPayload: When the decisions are malformed.
        """
        self._get_application(application_id)
        fields = list(self._fields.get_by_application(application_id))
        if not fields:
            raise ReviewNotRequired()
        pending = [
            field
            for field in fields
            if field.verification_status == FieldVerificationStatus.PENDING_REVIEW.value
        ]
        if not pending:
            raise ReviewAlreadyApplied()

        flagged_names = {field.field_name for field in pending}
        validate_review_request(request, flagged_names)

        try:
            halted = False
            decided: dict[str, str] = {}
            for decision in request.decisions:
                targets = [field for field in pending if field.field_name == decision.field_name]
                for field in targets:
                    self._apply_decision(
                        application_id=application_id,
                        field=field,
                        decision=decision.decision,
                        corrected_value=decision.corrected_value,
                        reviewer_name=reviewer_name,
                        commit=False,
                    )
                    decided[field.field_name] = decision.decision.value
                if decision.decision is ReviewDecisionType.CANNOT_VERIFY:
                    halted = True

            status = (
                EvaluationStatus.PROCESSING_HALTED
                if halted
                else EvaluationStatus.READY_FOR_NORMALIZATION
            )
            # The summary audit writes must share the transaction with the
            # field mutations: everything commits together once below, so a
            # failed audit write rolls the review back instead of leaving an
            # unaudited business change.
            self._audit.create(
                application_id=application_id,
                username=reviewer_name,
                action=ACTION_REVIEWED,
                details={"status": status.value, "decisions": decided},
                commit=False,
            )
            if halted:
                self._audit.create(
                    application_id=application_id,
                    username=reviewer_name,
                    action=ACTION_HALTED,
                    details={"status": status.value, "halted_fields": decided},
                    commit=False,
                )
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        logger.info(
            "Confidence review applied for application id=%s by reviewer=%s: "
            "status=%s decisions=%s",
            application_id,
            reviewer_name,
            status.value,
            sorted(decided),
        )
        return ReviewResponse(application_id=application_id, processing_status=status)

    # -- Internals ------------------------------------------------------------

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _collect_field_entries(
        self,
        results,
        documents: dict[int, Any],
        weights: dict[str, float],
    ) -> list[dict[str, Any]]:
        """Compute the raw confidence record for every extracted field."""
        entries: list[dict[str, Any]] = []
        for result in results:
            ocr_result = self._ocr_results.get_by_document(result.document_id)
            if ocr_result is None:  # pragma: no cover - analysis guarantees one
                continue
            ocr_confidence = ocr_result.overall_confidence
            expected = set(EXPECTED_FIELDS.get(result.document_type, frozenset()))
            present = set(result.extracted_fields or {})
            coverage = template_coverage(expected, present)
            validations = result.validation_results or []
            file_name = (
                documents[result.document_id].original_filename
                if result.document_id in documents
                else "unknown"
            )
            for name, value in (result.extracted_fields or {}).items():
                if value is None:
                    continue
                validation_status = find_validation_status(validations, name)
                sources = {
                    SOURCE_REGEX: regex_source_confidence(validation_status),
                    SOURCE_TEMPLATE: coverage,
                    SOURCE_OCR: ocr_confidence,
                    SOURCE_AI: None,
                }
                score, primary = compute_field_confidence(weights, sources)
                value_str = str(value)
                entries.append(
                    {
                        "ocr_result_id": ocr_result.id,
                        "document_id": result.document_id,
                        "file_name": file_name,
                        "field_name": name,
                        "extracted_value": value_str,
                        "normalized_value": value_str if isinstance(value, str) else None,
                        "score": score,
                        "primary": primary,
                        "reason": build_confidence_reason(
                            validation_status, ocr_confidence, coverage
                        ),
                        "resolved": False,
                        "status": None,
                    }
                )
        return entries

    def _mark_human_resolved(self, entries: list[dict[str, Any]]) -> None:
        """Preserve the state of fields a human already verified.

        A re-evaluation must never overwrite a completed human review: fields
        whose stored row is human-verified keep their stored score, source,
        reason and status and are excluded from the review decision.
        """
        for entry in entries:
            existing = self._fields.get_by_ocr_result_and_name(
                entry["ocr_result_id"], entry["field_name"]
            )
            if existing is not None and existing.human_verified:
                entry["resolved"] = True
                entry["extracted_value"] = existing.extracted_value
                entry["score"] = existing.confidence_score
                entry["primary"] = existing.confidence_source or entry["primary"]
                entry["reason"] = existing.confidence_reason or entry["reason"]
                entry["status"] = existing.verification_status

    @staticmethod
    def _overall_confidence(entries: list[dict[str, Any]]) -> float | None:
        """Return the mean field confidence, or ``None`` when nothing was scored."""
        if not entries:
            return None
        return sum(entry["score"] for entry in entries) / len(entries)

    def _apply_decision(
        self,
        *,
        application_id: int,
        field: ExtractedField,
        decision: ReviewDecisionType,
        corrected_value: str | None,
        reviewer_name: str,
        commit: bool,
    ) -> None:
        """Apply one employee decision to a pending field row.

        Args:
            application_id: Id of the application being reviewed.
            field: The pending field row to mutate.
            decision: The reviewer's decision.
            corrected_value: Corrected value, when the decision is CORRECTED.
            reviewer_name: Identity of the reviewer.
            commit: Whether the audit (and feedback) writes commit immediately
                or are deferred to the caller's single transaction. ``review``
                passes ``False`` so the mutation, feedback sample and audit
                entry all commit together.
        """
        if decision is ReviewDecisionType.VERIFIED:
            field.human_verified = True
            field.reviewer = reviewer_name
            field.reviewed_at = datetime.now(UTC)
            field.verification_status = FieldVerificationStatus.VERIFIED.value
            field.confidence_score = 1.0
            self._audit.create(
                application_id=application_id,
                username=reviewer_name,
                action=ACTION_VERIFIED,
                details={"field_name": field.field_name},
                commit=commit,
            )
            logger.info(
                "Field %s verified for application id=%s",
                field.field_name,
                application_id,
            )
            return

        if decision is ReviewDecisionType.CORRECTED:
            original_value = field.extracted_value
            original_confidence = field.confidence_score
            field.human_verified = True
            field.human_corrected_value = corrected_value
            field.reviewer = reviewer_name
            field.reviewed_at = datetime.now(UTC)
            field.extracted_value = corrected_value or ""
            field.verification_status = FieldVerificationStatus.CORRECTED.value
            field.confidence_score = 1.0
            self._audit.create(
                application_id=application_id,
                username=reviewer_name,
                action=ACTION_CORRECTED,
                details={"field_name": field.field_name},
                commit=commit,
            )
            self._feedback.create(
                application_id=application_id,
                field_name=field.field_name,
                human_value=corrected_value or "",
                ocr_value=original_value,
                confidence_score=original_confidence,
                document_id=field.ocr_result.document_id,
                ocr_result_id=field.ocr_result_id,
                normalized_value=field.normalized_value,
                confidence_source=field.confidence_source,
                reviewer=reviewer_name,
                decision=ReviewDecisionType.CORRECTED.value,
                origin=ORIGIN_LOW_CONFIDENCE_REVIEW,
                commit=commit,
            )
            logger.info(
                "Field %s corrected for application id=%s (feedback recorded)",
                field.field_name,
                application_id,
            )
            return

        field.verification_status = FieldVerificationStatus.CANNOT_VERIFY.value
        field.reviewer = reviewer_name
        field.reviewed_at = datetime.now(UTC)
        self._audit.create(
            application_id=application_id,
            username=reviewer_name,
            action=ACTION_CANNOT_VERIFY,
            details={"field_name": field.field_name},
            commit=commit,
        )
        logger.warning(
            "Field %s cannot be verified for application id=%s; processing halted",
            field.field_name,
            application_id,
        )

    def _to_field_result(self, entry: dict[str, Any]) -> FieldConfidenceResult:
        """Map a stored field row onto the response schema."""
        row = entry["row"]
        return FieldConfidenceResult(
            document_id=entry["document_id"],
            file_name=entry["file_name"],
            field_name=entry["field_name"],
            extracted_value=row.extracted_value,
            normalized_value=row.normalized_value,
            confidence_score=row.confidence_score,
            confidence_source=row.confidence_source,
            confidence_reason=row.confidence_reason,
            verification_status=row.verification_status,
            critical=is_critical(entry["field_name"]),
            human_corrected_value=row.human_corrected_value,
            human_verified=row.human_verified,
            reviewer=row.reviewer,
            reviewed_at=row.reviewed_at,
        )


__all__ = [
    "ConfidenceService",
    "build_confidence_reason",
    "compute_field_confidence",
    "decide_processing_status",
    "find_validation_status",
    "regex_source_confidence",
    "template_coverage",
]
