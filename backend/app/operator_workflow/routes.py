"""HTTP endpoints for the operator validation workflow.

Exposes the operator validation queue, per-application history, and the three
operator actions (request documents, reject, submit). Queue and history are
readable by every authenticated role; the three actions require the OPERATOR
role (403 for any other role). The reviewer's detailed workflow lives in the
human-verification module.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.roles import ROLE_OPERATOR
from app.database.connection import get_db
from app.database.models.user import User
from app.operator_workflow.exceptions import OperatorWorkflowError
from app.operator_workflow.schemas import (
    ErrorResponse,
    OperatorActionResponse,
    OperatorRejectRequest,
    RequestDocumentsRequest,
    ValidationHistoryResponse,
    ValidationQueueResponse,
)
from app.operator_workflow.services import OperatorWorkflowService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["operator-workflow"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Requires the operator role."},
    404: {"model": ErrorResponse, "description": "Application not found."},
    409: {"model": ErrorResponse, "description": "Invalid status transition."},
    422: {"model": ErrorResponse, "description": "Validation failed for the action."},
    500: {"model": ErrorResponse, "description": "Unexpected failure."},
}


def _handle_operator_errors(func):
    """Translate :class:`OperatorWorkflowError` into HTTP error responses."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except OperatorWorkflowError as exc:
            logger.error(
                "Operator workflow error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> OperatorWorkflowService:
    """Build the operator workflow service bound to the request session."""
    return OperatorWorkflowService(db)


@router.get(
    "/validation/applications",
    response_model=ValidationQueueResponse,
    summary="List applications in the operator validation queue",
    description=(
        "Returns every application with business-level completeness details, "
        "ordered so pending/needs-attention applications come first. "
        "Deliberately excludes OCR, confidence and processing internals."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_operator_errors
def list_validation_queue(
    db: _GET_DB,
    offset: int = 0,
    limit: int = 50,
) -> ValidationQueueResponse:
    """Return the operator validation queue."""
    items, total = _service(db).list_queue(offset=offset, limit=limit)
    return ValidationQueueResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/applications/{application_id}/validation-history",
    response_model=ValidationHistoryResponse,
    summary="List an application's validation history",
    description=(
        "Returns the immutable, append-only validation workflow history for an "
        "application, newest first, so repeated document submissions are never "
        "overwritten."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_operator_errors
def get_validation_history(
    application_id: int,
    db: _GET_DB,
    offset: int = 0,
    limit: int = 50,
) -> ValidationHistoryResponse:
    """Return an application's validation history."""
    entries, total = _service(db).get_history(
        application_id=application_id, offset=offset, limit=limit
    )
    return ValidationHistoryResponse(
        application_id=application_id,
        entries=entries,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/applications/{application_id}/request-documents",
    response_model=OperatorActionResponse,
    summary="Request missing documents from the applicant",
    description=(
        "Moves an application to NEEDS_DOCUMENTS and records the requested "
        "document types, the operator and a timestamp in the validation "
        "history and audit log."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_operator_errors
def request_documents(
    application_id: int,
    payload: RequestDocumentsRequest,
    db: _GET_DB,
    current_user: User = Depends(require_role(ROLE_OPERATOR)),
) -> OperatorActionResponse:
    """Request missing documents for an application."""
    return _service(db).request_documents(
        application_id=application_id,
        missing_document_types=[
            document_type.value for document_type in payload.missing_document_types
        ],
        reason=payload.reason,
        user=current_user,
    )


@router.post(
    "/applications/{application_id}/operator-reject",
    response_model=OperatorActionResponse,
    summary="Reject an application at the operator stage",
    description=(
        "Rejects an application that cannot proceed, recording the operator "
        "and reason in the validation history and audit log."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_operator_errors
def reject_application(
    application_id: int,
    payload: OperatorRejectRequest,
    db: _GET_DB,
    current_user: User = Depends(require_role(ROLE_OPERATOR)),
) -> OperatorActionResponse:
    """Reject an application at the operator stage."""
    return _service(db).reject_application(
        application_id=application_id, reason=payload.reason, user=current_user
    )


@router.post(
    "/applications/{application_id}/operator-submit",
    response_model=OperatorActionResponse,
    summary="Submit a complete application for processing",
    description=(
        "Verifies document completeness (422 if anything is missing) then "
        "enqueues the application for processing and moves it to PROCESSING."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_operator_errors
def submit_application(
    application_id: int,
    db: _GET_DB,
    current_user: User = Depends(require_role(ROLE_OPERATOR)),
) -> OperatorActionResponse:
    """Submit a complete application for processing."""
    return _service(db).submit_application(application_id=application_id, user=current_user)