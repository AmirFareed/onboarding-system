"""HTTP endpoints for the Performance API.

IT-only, read-only view of application turnaround timing. Every endpoint
requires the canonical IT role exactly; the Employee superuser shortcut is not
accepted for this business-reporting surface.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_exact_role
from app.auth.roles import ROLE_IT
from app.database.connection import get_db
from app.database.models.enums import ApplicationStatus
from app.performance.schemas import (
    ErrorResponse,
    PerformanceApplicationsResponse,
    PerformanceOverview,
)
from app.performance.services import PerformanceService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["performance"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Requires the IT role."},
    422: {"model": ErrorResponse, "description": "Invalid query parameters."},
    500: {"model": ErrorResponse, "description": "Unexpected failure."},
}


def _handle_performance_errors(func):
    """Translate service errors into HTTP error responses."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Performance error %s: %s", exc.__class__.__name__, exc)
            raise HTTPException(status_code=500, detail="Unexpected failure") from exc

    return wrapper


def _service(db: Session) -> PerformanceService:
    """Build the performance service bound to the request session."""
    return PerformanceService(db)


@router.get(
    "/performance/overview",
    response_model=PerformanceOverview,
    summary="Get aggregate performance across all applications",
    description=(
        "Returns aggregate turnaround, processing, waiting-for-documents and "
        "review times averaged across applications. Averages are computed only "
        "over applications that actually have the metric (e.g. turnaround is "
        "averaged over decided applications only), so a set of all-in-flight "
        "applications reports no misleading figures. Also returns status "
        "counts, total resubmissions and missing-document cycles."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_performance_errors
def get_overview(
    db: _GET_DB,
    _: None = Depends(require_exact_role(ROLE_IT)),
) -> PerformanceOverview:
    """Return aggregate performance figures."""
    return _service(db).overview()


@router.get(
    "/performance/applications",
    response_model=PerformanceApplicationsResponse,
    summary="List per-application performance with supporting evidence",
    description=(
        "Returns a paginated list of per-application timing breakdowns. Every "
        "row carries the individual time spans behind its numbers (document "
        "request/receipt pairs, queue-job runs, review windows) so the UI can "
        "drill from a headline figure to the exact events that produced it. "
        "Searchable by id/name/submitter and filterable by status."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_performance_errors
def list_applications(
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
) -> PerformanceApplicationsResponse:
    """Return the paginated per-application performance rows."""
    items, total = _service(db).list_applications(
        offset=offset, limit=limit, query=query, status=status
    )
    return PerformanceApplicationsResponse(
        items=items, total=total, offset=offset, limit=limit
    )
