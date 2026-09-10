"""Business rule validation service.

Runs the deterministic ruleset against an application's normalized, verified
evidence, persists one :class:`ValidationResult` row per executed rule (reusing
the Phase 2 table with the rule-engine categories) and reports the outcome.
A rule that raises is never allowed to abort the run: it is logged and recorded
as a failed rule, so every rule always produces a visible result. Each run
replaces the previous run's rule rows, giving the stored results replace
semantics.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.database.models.enums import Severity, ValidationStatus
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.extracted_field_repository import ExtractedFieldRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.database.repositories.validation_repository import ValidationRepository
from app.database.repositories.visual_detection_repository import VisualDetectionRepository
from app.normalization.constants import SKIPPED_VERIFICATION_STATUSES
from app.rule_engine.constants import (
    ACTION_VALIDATED,
    OVERALL_STATUS_PRECEDENCE,
    RULE_CATEGORIES,
    RULE_CATEGORY_KEYS,
    RULE_ENGINE_VERSION,
    SEVERITY_FAIL,
    SEVERITY_PASS,
    SEVERITY_WARNING,
)
from app.rule_engine.exceptions import ApplicationNotFound
from app.rule_engine.rules import REGISTRY
from app.rule_engine.rules.base import BaseRule
from app.rule_engine.schemas import (
    FieldValue,
    RuleCategorySummary,
    RuleContext,
    RuleEngineResponse,
    RuleResult,
    RuleResultItem,
    RuleRunSummary,
    StoredRuleResult,
    ValidationResultsResponse,
    category_label,
)

logger = logging.getLogger(__name__)


class RuleEngineService:
    """Validates an application against the business ruleset.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._ocr_results = OCRRepository(db)
        self._fields = ExtractedFieldRepository(db)
        self._detections = VisualDetectionRepository(db)
        self._validation = ValidationRepository(db)
        self._audit = AuditLogRepository(db)
        self._registry = REGISTRY

    # -- Public API -----------------------------------------------------------

    def validate(self, *, application_id: int) -> RuleEngineResponse:
        """Run every business rule against an application and persist the results.

        Each rule is executed independently; a rule-level failure is captured in
        its own result and never aborts the run. Results are persisted with the
        ``validated_at`` timestamp shared by the whole run, replacing any
        previously stored rule-engine rows so the stored results always mirror
        the latest run.

        Args:
            application_id: Id of the application to validate.

        Returns:
            The complete rule validation outcome.

        Raises:
            ApplicationNotFound: When the application does not exist.
            RuleEngineError: When the run fails unexpectedly.
        """
        application = self._get_application(application_id)
        context = self._build_context(application_id)
        logger.info(
            "Business rule validation started for application id=%s (%s documents)",
            application.id,
            len(context.documents_by_type),
        )
        run_at = datetime.now(UTC)

        results: list[RuleResult] = []
        for rule in self._registry.rules():
            result = self._execute_rule(rule, context)
            results.append(result.with_validated_at(run_at))

        self._persist_results(application_id, results)
        response = self._build_response(application_id, run_at, results)
        self._audit.create(
            application_id=application_id,
            username="system",
            action=ACTION_VALIDATED,
            details={
                "status": response.validation_status.value,
                "version": RULE_ENGINE_VERSION,
                "summary": response.summary.model_dump(),
            },
        )
        logger.info(
            "Business rule validation completed for application id=%s: "
            "overall_status=%s total=%s passed=%s failed=%s warnings=%s pending=%s",
            application_id,
            response.validation_status.value,
            response.summary.total,
            response.summary.passed,
            response.summary.failed,
            response.summary.warnings,
            response.summary.pending_review,
        )
        return response

    def get_results(
        self,
        *,
        application_id: int,
        category: str | None = None,
    ) -> ValidationResultsResponse:
        """Return the stored rule-engine validation results for an application.

        Only rows whose category belongs to the rule engine's own categories are
        returned, so technical validation rows are never mixed in.

        Args:
            application_id: Id of the application.
            category: Optional category to filter on (a key of
                ``RULE_CATEGORIES``).

        Returns:
            The stored per-rule outcome rows.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        self._get_application(application_id)
        categories = {category} if category else set(RULE_CATEGORY_KEYS)
        rows = self._validation.get_by_application_and_categories(
            application_id,
            categories,
        )
        logger.info(
            "Returned %s stored rule-engine results for application id=%s",
            len(rows),
            application_id,
        )
        return ValidationResultsResponse(
            application_id=application_id,
            total=len(rows),
            results=[self._stored_result(row) for row in rows],
        )

    # -- Internals ------------------------------------------------------------

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _build_context(self, application_id: int) -> RuleContext:
        """Assemble the context every rule inspects for an application.

        Documents are grouped by type; extracted fields are flattened into plain
        value records carrying their document id and type; detection outcomes are
        keyed by document id and detection kind.

        Args:
            application_id: Id of the application to validate.

        Returns:
            The assembled rule context.
        """
        documents = list(self._documents.get_all_by_application(application_id))
        documents_by_type: dict[str, list[int]] = {}
        document_types: dict[int, str] = {}
        for document in documents:
            documents_by_type.setdefault(document.document_type.value, []).append(
                document.id
            )
            document_types[document.id] = document.document_type.value

        document_ids: dict[int, int] = {
            ocr_result.id: ocr_result.document_id
            for ocr_result in self._ocr_results.get_by_application(application_id)
        }
        fields: list[FieldValue] = []
        for field in self._fields.get_by_application(application_id):
            document_id = document_ids.get(field.ocr_result_id)
            if document_id is None:  # pragma: no cover - FK keeps these aligned
                continue
            normalized_value = field.normalized_value
            if (
                normalized_value
                and field.verification_status in SKIPPED_VERIFICATION_STATUSES
            ):
                logger.info(
                    "Ignoring stale normalized value for field %s "
                    "(document id=%s, status=%s)",
                    field.field_name,
                    document_id,
                    field.verification_status,
                )
                normalized_value = None
            fields.append(
                FieldValue(
                    field_name=field.field_name,
                    document_id=document_id,
                    document_type=document_types.get(document_id, "UNKNOWN"),
                    extracted_value=field.extracted_value,
                    normalized_value=normalized_value,
                    verification_status=field.verification_status,
                    confidence_score=field.confidence_score,
                )
            )

        detections = {
            (detection.document_id, detection.detection_type): detection.is_present
            for detection in self._detections.get_by_application(application_id)
        }
        return RuleContext(
            application_id=application_id,
            documents_by_type=documents_by_type,
            fields=fields,
            detections=detections,
        )

    def _execute_rule(self, rule: BaseRule, context: RuleContext) -> RuleResult:
        """Execute one rule, never letting an exception escape the run.

        Args:
            rule: Rule to execute.
            context: Application context.

        Returns:
            The rule's outcome; a failed rule when the execution raised.
        """
        try:
            result = rule.evaluate(context)
            logger.info(
                "Rule %s executed (application id=%s): status=%s",
                rule.id,
                context.application_id,
                result.status.value,
            )
            return result
        except Exception as exc:
            logger.exception(
                "Rule %s failed during execution (application id=%s)",
                rule.id,
                context.application_id,
            )
            return RuleResult(
                rule_id=rule.id,
                rule_name=rule.name,
                category=rule.category,
                status=ValidationStatus.FAIL,
                message=f"Rule execution failed unexpectedly: {exc}",
            )

    def _persist_results(
        self,
        application_id: int,
        results: list[RuleResult],
    ) -> None:
        """Replace the stored rule rows with the fresh run's results.

        Args:
            application_id: Application being validated.
            results: Outcomes of the current run, already time-stamped.
        """
        self._validation.delete_by_application_and_categories(
            application_id,
            RULE_CATEGORY_KEYS,
        )
        for result in results:
            self._validation.create(
                application_id=application_id,
                rule_id=result.rule_id,
                rule_name=result.rule_name,
                rule_category=result.category,
                severity=_severity_for(result.status),
                status=result.status,
                message=result.message,
                related_document_ids=result.related_document_ids or None,
                related_field_names=result.related_field_names or None,
                validated_at=result.validated_at,
            )

    def _build_response(
        self,
        application_id: int,
        run_at: datetime,
        results: list[RuleResult],
    ) -> RuleEngineResponse:
        """Assemble the run response, summaries and per-rule items.

        Args:
            application_id: Validated application.
            run_at: Shared timestamp of the run.
            results: Outcomes of the run.

        Returns:
            The serializable run outcome.
        """
        items = [self._item(result) for result in results]
        summary = RuleRunSummary(total=len(results))
        category_summary = {
            category: RuleCategorySummary(category=category, category_label=label)
            for category, label in RULE_CATEGORIES.items()
        }
        for result in results:
            _tally(summary, result.status)
            _tally(category_summary[result.category], result.status)
        return RuleEngineResponse(
            application_id=application_id,
            validation_status=_overall_status(results),
            validated_at=run_at,
            summary=summary,
            category_summary=list(category_summary.values()),
            results=items,
        )

    @staticmethod
    def _item(result: RuleResult) -> RuleResultItem:
        """Convert a run result into the response item model."""
        return RuleResultItem(
            rule_id=result.rule_id,
            rule_name=result.rule_name,
            category=result.category,
            category_label=category_label(result.category),
            status=result.status,
            severity=_severity_for(result.status).value,
            message=result.message,
            related_document_ids=result.related_document_ids,
            related_field_names=result.related_field_names,
            validated_at=result.validated_at,
        )

    @staticmethod
    def _stored_result(row) -> StoredRuleResult:
        """Convert a stored validation row into the response item model."""
        return StoredRuleResult(
            rule_id=row.rule_id,
            rule_name=row.rule_name,
            rule_category=row.rule_category,
            category_label=category_label(row.rule_category),
            status=row.status,
            severity=row.severity.value,
            message=row.message,
            related_document_ids=row.related_document_ids or [],
            related_field_names=row.related_field_names or [],
            validated_at=row.validated_at,
        )


def _severity_for(status: ValidationStatus) -> Severity:
    """Derive the stored severity from a rule's status.

    Args:
        status: Rule status.

    Returns:
        ``ERROR`` for failed rules, ``WARNING`` for warnings and pending rules,
        ``INFO`` for passed rules.
    """
    if status is ValidationStatus.FAIL:
        return SEVERITY_FAIL
    if status is ValidationStatus.WARNING or status is ValidationStatus.PENDING_MANUAL_REVIEW:
        return SEVERITY_WARNING
    return SEVERITY_PASS


def _tally(target, status: ValidationStatus) -> None:
    """Increment the summary counter matching ``status`` on ``target``."""
    if status is ValidationStatus.PASS:
        target.passed += 1
    elif status is ValidationStatus.FAIL:
        target.failed += 1
    elif status is ValidationStatus.WARNING:
        target.warnings += 1
    else:
        target.pending_review += 1


def _overall_status(results: list[RuleResult]) -> ValidationStatus:
    """Derive the overall run status by strictest-first precedence.

    Args:
        results: Outcomes of the run.

    Returns:
        The status that wins the precedence ordering.
    """
    for status in OVERALL_STATUS_PRECEDENCE:
        if any(result.status is status for result in results):
            return status
    return ValidationStatus.PASS


__all__ = ["RuleEngineService"]
