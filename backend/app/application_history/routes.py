"""HTTP endpoints for the Application History API.

IT-only, read-only projection of application lifecycle data. Every endpoint
requires the canonical IT role exactly; the Employee superuser shortcut is not
accepted for this business-reporting surface. No application data is mutated.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.application_history.schemas import (
    ApplicationHistoryListResponse,
    ApplicationTimelineResponse,
    ErrorResponse,
    TimelineEvent,
)
from app.application_history.services import (
    ApplicationHistoryService,
    ApplicationNotFoundError,
)
from app.auth.dependencies import require_exact_role
from app.auth.roles import ROLE_IT
from app.database.connection import get_db
from app.database.models.enums import ApplicationStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["application-history"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Requires the IT role."},
    404: {"model": ErrorResponse, "description": "Application not found."},
    422: {"model": ErrorResponse, "description": "Invalid query parameters."},
    500: {"model": ErrorResponse, "description": "Unexpected failure."},
}


def _handle_history_errors(func):
    """Translate service errors into HTTP error responses."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ApplicationNotFoundError as exc:
            logger.error("Application history error %s: %s", exc.__class__.__name__, exc)
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return wrapper


def _service(db: Session) -> ApplicationHistoryService:
    """Build the application history service bound to the request session."""
    return ApplicationHistoryService(db)


@router.get(
    "/applications/history",
    response_model=ApplicationHistoryListResponse,
    summary="List applications for the IT history view",
    description=(
        "Returns a paginated list of every application with its current status "
        "and the most recent workflow event (document request, upload, review "
        "decision, etc.), searchable by id/name/submitter and filterable by "
        "status. Newest submissions first."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_history_errors
def list_history(
    db: _GET_DB,
    _: None = Depends(require_exact_role(ROLE_IT)),
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    query: Annotated[
        str | None,
        Query(description="Free-text search on id/name/submitter."),
    ] = None,
    status: ApplicationStatus | None = Query(
        default=None,
        description="When given, only return applications in this status.",
    ),
) -> ApplicationHistoryListResponse:
    """Return the paginated application history list."""
    items, total = _service(db).list_applications(
        offset=offset, limit=limit, query=query, status=status
    )
    return ApplicationHistoryListResponse(
        items=items, total=total, offset=offset, limit=limit
    )


@router.get(
    "/applications/{application_id}/timeline",
    response_model=ApplicationTimelineResponse,
    summary="Get an application's full lifecycle timeline",
    description=(
        "Returns a single application's complete business timeline in "
        "chronological order: creation, document uploads, document requests and "
        "receipts, processing completion and the final review decision. Every "
        "event carries only business-facing fields (actor, label, timestamp) "
        "with no raw internals."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_history_errors
def get_timeline(
    application_id: int,
    db: _GET_DB,
    _: None = Depends(require_exact_role(ROLE_IT)),
) -> ApplicationTimelineResponse:
    """Return one application's full timeline."""
    service = _service(db)
    application = service.get_timeline(application_id)
    if application is None:
        raise HTTPException(
            status_code=404, detail=f"Application {application_id} not found"
        )
    events: list[TimelineEvent] = service.timeline(application_id)
    return ApplicationTimelineResponse(
        application_id=application.id,
        application_name=application.name,
        status=application.status,
        submitted_at=application.submitted_at,
        created_by=application.created_by,
        events=events,
    )
