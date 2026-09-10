"""Runs the post-OCR verification pipeline for one application.

Chains the four stages that were previously only reachable by calling their
own HTTP endpoints directly -- something nothing in this codebase actually
did (confirmed by reading every service and grepping the frontend): document
analysis, confidence evaluation, normalization and business-rule validation.
The required order is not the one implied by the README's pipeline diagram;
it's fixed by a real data dependency confirmed by reading each service:
confidence is the *only* writer of ``extracted_fields`` rows, and
normalization requires that table to be non-empty. So analysis must run
before confidence, and confidence before normalization, or normalization
raises ``NoExtractedFields`` immediately.

Invoked by :class:`app.bulk_queue.workers.BulkQueueWorker` for
``APPLICATION_PIPELINE`` jobs, once every ``DOCUMENT_OCR`` job of an
application has reached a terminal state. Each stage already tolerates
missing/partial per-document or per-field data on its own (see their
docstrings -- "the run always completes"); the only failures this can
realistically raise are genuine bugs or database errors, which propagate to
the caller and are retried by the same queue machinery already proven for
OCR jobs.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.confidence.services import ConfidenceService
from app.database.models.enums import ApplicationStatus
from app.database.repositories.application_repository import ApplicationRepository
from app.document_analysis.services import DocumentAnalysisService
from app.normalization.services import NormalizationService
from app.rule_engine.services import RuleEngineService

logger = logging.getLogger(__name__)


class PipelineStageFailed(RuntimeError):
    """A pipeline stage raised while running the chain for an application."""

    def __init__(self, stage: str, original: Exception) -> None:
        super().__init__(f"Pipeline stage '{stage}' failed: {original}")
        self.stage = stage
        self.original = original


class PipelineRunnerService:
    """Runs analysis, confidence, normalization and rule validation in order.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def run(self, *, application_id: int) -> None:
        """Run every post-OCR stage for an application, in the required order.

        Args:
            application_id: Application whose documents have all finished OCR.

        Raises:
            PipelineStageFailed: When a stage raises unexpectedly. The
                original exception is attached for logging/inspection.
        """
        self._run_stage("analysis", lambda: DocumentAnalysisService(self._db).analyze(
            application_id=application_id
        ))
        self._run_stage("confidence", lambda: ConfidenceService(self._db).evaluate(
            application_id=application_id
        ))
        self._run_stage("normalization", lambda: NormalizationService(self._db).normalize(
            application_id=application_id
        ))
        self._run_stage("rule_validation", lambda: RuleEngineService(self._db).validate(
            application_id=application_id
        ))
        self._run_stage("mark_pending_review", lambda: self._mark_pending_review(application_id))
        logger.info("Pipeline completed for application id=%s", application_id)

    def _mark_pending_review(self, application_id: int) -> None:
        """Move the application to PENDING_REVIEW now that a report exists.

        Guarded to only fire from PROCESSING so a retried pipeline job (this
        method can run more than once for the same application if an earlier
        attempt raised) never regresses a status a human has since decided.
        """
        applications = ApplicationRepository(self._db)
        application = applications.get_by_id(application_id)
        if application is not None and application.status is ApplicationStatus.PROCESSING:
            applications.update(application, status=ApplicationStatus.PENDING_REVIEW)

    def _run_stage(self, name: str, call) -> None:
        try:
            call()
        except Exception as exc:
            logger.exception(
                "Pipeline stage '%s' failed for this run", name
            )
            raise PipelineStageFailed(name, exc) from exc
