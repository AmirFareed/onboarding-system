"""Operator validation workflow service.

Coordinates the first-level operator queue and the three operator actions:
request-documents, operator-reject and operator-submit. Every action is a
single self-contained transaction that updates the application status (guarded
to the expected prior status, following the codebase's inline-guard convention),
appends an immutable :class:`ValidationHistoryEntry` and writes an
:class:`AuditLog`, so repeated document submissions preserve full history.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.database.models.application import Application
from app.database.models.enums import ApplicationStatus, ValidationEventType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.validation_history_repository import (
    ValidationHistoryRepository,
)
from app.operator_workflow.exceptions import (
    ApplicationComplete,
    ApplicationNotFound,
    IncompleteApplication,
    InvalidTransition,
    MissingReason,
)
from app.operator_workflow.schemas import (
    DocumentStatusSummary,
    OperatorActionResponse,
    ValidationHistoryEntryRead,
    ValidationQueueItem,
)

logger = logging.getLogger(__name__)

#: Statuses from which an operator may request documents.
REQUEST_DOCUMENTS_PRIOR_STATUSES = frozenset(
    {ApplicationStatus.SUBMITTED, ApplicationStatus.NEEDS_DOCUMENTS}
)

#: Statuses from which an operator may reject an application.
OPERATOR_REJECT_PRIOR_STATUSES = frozenset(
    {
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.NEEDS_DOCUMENTS,
        ApplicationStatus.PROCESSING_FAILED,
    }
)

#: Statuses from which an operator may submit an application for processing.
OPERATOR_SUBMIT_PRIOR_STATUSES = frozenset(
    {ApplicationStatus.SUBMITTED, ApplicationStatus.NEEDS_DOCUMENTS}
)


class OperatorWorkflowService:
    """Backs the operator validation queue and actions."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._history = ValidationHistoryRepository(db)
        self._audit = AuditLogRepository(db)

    # -- Queue -----------------------------------------------------------

    def list_queue(self, *, offset: int = 0, limit: int = 50) -> tuple[list[ValidationQueueItem], int]:
        """Return the operator queue, ordered by attention then recency.

        Ordering (per the operator workflow spec): pending/needs-attention
        first, then under review, then processing, then accepted, then
        rejected. Within each group applications are newest first.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A tuple of queue items and the total application count.
        """
        from app.completeness.services import CompletenessService

        applications = list(self._applications.list(offset=0, limit=10000))
        items = []
        for application in applications:
            report = CompletenessService(self._db).get_report(application_id=application.id)
            last = self._history.latest_for_application(application.id)
            needs_attention = (
                application.status is ApplicationStatus.NEEDS_DOCUMENTS
                or application.status is ApplicationStatus.PROCESSING_FAILED
                or bool(report.missing_documents)
            )
            items.append(
                ValidationQueueItem(
                    application_id=application.id,
                    application_name=application.name,
                    status=application.status,
                    submitted_at=application.submitted_at,
                    updated_at=application.updated_at,
                    created_by=application.created_by,
                    required_document_count=len(report.required_documents),
                    received_document_count=sum(
                        1 for doc in report.required_documents if doc.is_present
                    ),
                    missing_document_count=len(report.missing_documents),
                    missing_documents=list(report.missing_documents),
                    required_documents=[
                        DocumentStatusSummary(**status.model_dump())
                        for status in report.required_documents
                    ],
                    completion_percentage=report.completion_percentage,
                    needs_attention=needs_attention,
                    last_event_type=last.event_type if last else None,
                    last_event_at=last.created_at if last else None,
                )
            )

        items.sort(
            key=lambda item: (
                _queue_rank(item.status),
                item.needs_attention is not True,
                item.updated_at.timestamp(),
            )
        )
        total = len(items)
        return items[offset : offset + limit], total

    # -- History ---------------------------------------------------------

    def get_history(
        self,
        *,
        application_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ValidationHistoryEntryRead], int]:
        """Return an application's validation history, newest first."""
        self._get_application(application_id)
        entries, total = self._history.list_for_application(
            application_id, offset=offset, limit=limit
        )
        return [ValidationHistoryEntryRead.model_validate(entry) for entry in entries], total

    # -- Actions ---------------------------------------------------------

    def request_documents(
        self,
        *,
        application_id: int,
        missing_document_types: list[str],
        reason: str | None,
        user,
    ) -> OperatorActionResponse:
        """Mark an application as needing documents and record the request."""
        application = self._get_application(application_id)
        if not missing_document_types:
            raise ApplicationComplete()

        missing = list(missing_document_types)
        previous = application.status
        if previous not in REQUEST_DOCUMENTS_PRIOR_STATUSES:
            raise InvalidTransition()

        application = self._applications.update(
            application, status=ApplicationStatus.NEEDS_DOCUMENTS
        )
        entry = self._history.create(
            application_id=application.id,
            event_type=ValidationEventType.DOCUMENTS_REQUESTED,
            actor_id=user.id,
            actor_name=user.name,
            actor_role=user.role,
            previous_status=previous.value,
            new_status=application.status.value,
            missing_document_types=missing,
            reason=reason,
        )
        self._audit.create(
            application_id=application.id,
            username=user.name,
            action="DOCUMENTS_REQUESTED",
            details={"missing_document_types": missing, "reason": reason},
            actor_id=user.id,
            actor_role=user.role,
            severity="WARNING",
            previous_status=previous.value,
            new_status=application.status.value,
        )
        logger.info(
            "Operator %s requested documents for application id=%s: %s",
            user.name,
            application.id,
            missing,
        )
        return OperatorActionResponse(
            application_id=application.id,
            status=application.status,
            message="Documents requested",
            history_entry_id=entry.id,
        )

    def reject_application(
        self, *, application_id: int, reason: str, user
    ) -> OperatorActionResponse:
        """Reject an application that cannot proceed, recording the decision."""
        if not reason or not reason.strip():
            raise MissingReason()
        application = self._get_application(application_id)
        previous = application.status
        if previous not in OPERATOR_REJECT_PRIOR_STATUSES:
            raise InvalidTransition()

        application = self._applications.update(application, status=ApplicationStatus.REJECTED)
        entry = self._history.create(
            application_id=application.id,
            event_type=ValidationEventType.OPERATOR_REJECTED,
            actor_id=user.id,
            actor_name=user.name,
            actor_role=user.role,
            previous_status=previous.value,
            new_status=application.status.value,
            reason=reason,
        )
        self._audit.create(
            application_id=application.id,
            username=user.name,
            action="OPERATOR_REJECTED",
            details={"reason": reason},
            actor_id=user.id,
            actor_role=user.role,
            severity="ERROR",
            previous_status=previous.value,
            new_status=application.status.value,
        )
        logger.info("Operator %s rejected application id=%s", user.name, application.id)
        return OperatorActionResponse(
            application_id=application.id,
            status=application.status,
            message="Application rejected",
            history_entry_id=entry.id,
        )

    def submit_application(self, *, application_id: int, user) -> OperatorActionResponse:
        """Submit a complete application for processing.

        Runs the completeness gate; a complete document set is required (422
        otherwise). Reuses the bulk queue enqueue path so the application moves
        to ``PROCESSING`` exactly as a manual "start processing" would.
        """
        from app.completeness.constants import CompletenessStatus
        from app.completeness.services import CompletenessService

        application = self._get_application(application_id)
        previous = application.status
        if previous not in OPERATOR_SUBMIT_PRIOR_STATUSES:
            raise InvalidTransition()

        report = CompletenessService(self._db).verify(application_id=application.id)
        if report.status is not CompletenessStatus.COMPLETE:
            raise IncompleteApplication()

        from app.bulk_queue.services import BulkQueueService

        BulkQueueService(self._db).enqueue_application(application_id=application.id)
        application = self._applications.get_by_id(application.id)
        if application.status is ApplicationStatus.NEEDS_DOCUMENTS:
            # The bulk queue path only transitions SUBMITTED -> PROCESSING; an
            # application coming out of NEEDS_DOCUMENTS needs the same move here
            # so its status is PROCESSING once its documents are enqueued.
            application = self._applications.update(
                application, status=ApplicationStatus.PROCESSING
            )
        entry = self._history.create(
            application_id=application.id,
            event_type=ValidationEventType.SUBMITTED_FOR_PROCESSING,
            actor_id=user.id,
            actor_name=user.name,
            actor_role=user.role,
            previous_status=previous.value,
            new_status=application.status.value,
        )
        self._audit.create(
            application_id=application.id,
            username=user.name,
            action="OPERATOR_SUBMITTED",
            details={},
            actor_id=user.id,
            actor_role=user.role,
            severity="INFO",
            previous_status=previous.value,
            new_status=application.status.value,
        )
        logger.info("Operator %s submitted application id=%s for processing", user.name, application.id)
        return OperatorActionResponse(
            application_id=application.id,
            status=application.status,
            message="Application submitted for processing",
            history_entry_id=entry.id,
        )

    # -- Helpers ---------------------------------------------------------

    def _get_application(self, application_id: int) -> Application:
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application


def _queue_rank(status: ApplicationStatus) -> int:
    """Map an application status to its operator-queue ordering rank.

    Pending / needs operator attention first, then under review, then
    processing, then accepted, then rejected.
    """
    rank = {
        ApplicationStatus.SUBMITTED: 0,
        ApplicationStatus.NEEDS_DOCUMENTS: 0,
        ApplicationStatus.PROCESSING_FAILED: 0,
        ApplicationStatus.PENDING_REVIEW: 1,
        ApplicationStatus.PROCESSING: 2,
        ApplicationStatus.APPROVED: 3,
        ApplicationStatus.CORRECTED: 3,
        ApplicationStatus.REJECTED: 4,
    }
    return rank.get(status, 5)