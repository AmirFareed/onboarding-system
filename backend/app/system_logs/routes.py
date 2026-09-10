"""HTTP endpoints for the IT system-log API.

Every endpoint requires the IT role (403 for any other role). Logs are
read-only operational audit records -- never raw document contents or extracted
PII.
"""

import logging
from datetime import datetime
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.roles import ROLE_IT
from app.database.connection import get_db
from app.system_logs.schemas import ErrorResponse, SystemLogListResponse, SystemLogRead
from app.system_logs.services import SystemLogNotFound, SystemLogService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system-logs"])

_GET_DB = Annotated[Session, Depends(get_db)]

_ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Requires the IT role."},
    404: {"model": ErrorResponse, "description": "System log entry not found."},
    422: {"model": ErrorResponse, "description": "Invalid filter values."},
}


def _handle_system_log_errors(func):
    """Translate system-log domain errors into HTTP error responses."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SystemLogNotFound as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> SystemLogService:
    return SystemLogService(db)


@router.get(
    "/system-logs",
    response_model=SystemLogListResponse,
    summary="Search the system log",
    description=(
        "Returns audit log entries newest first, optionally filtered by "
        "application, actor, event type, severity and date range. Entries "
        "whose application was later deleted (orphaned) are excluded by "
        "default; pass include_orphaned=true to see everything. IT only."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_system_log_errors
def list_system_logs(
    db: _GET_DB,
    _current_user: object = Depends(require_role(ROLE_IT)),
    application_id: int | None = None,
    actor: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    query: str | None = None,
    offset: int = 0,
    limit: int = 50,
    include_orphaned: bool = False,
) -> SystemLogListResponse:
    """Search the system log (IT only)."""
    items, total = _service(db).search(
        offset=offset,
        limit=limit,
        application_id=application_id,
        actor=actor,
        event_type=event_type,
        severity=severity,
        date_from=date_from,
        date_to=date_to,
        query=query,
        include_orphaned=include_orphaned,
    )
    return SystemLogListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/system-logs/{log_id}",
    response_model=SystemLogRead,
    summary="Get a single system log entry",
    description="Returns one audit log entry by id. IT only.",
    responses=_ERROR_RESPONSES,
)
@_handle_system_log_errors
def get_system_log(
    log_id: int,
    db: _GET_DB,
    _current_user: object = Depends(require_role(ROLE_IT)),
) -> SystemLogRead:
    """Return a single system log entry (IT only)."""
    return _service(db).get(log_id=log_id)