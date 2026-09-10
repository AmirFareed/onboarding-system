"""HTTP endpoints for document completeness verification.

Exposes the read (``GET``) and verify (``POST``) endpoints. Both compute the
report from live document metadata via :class:`CompletenessService`; routes stay
thin and translate the module's domain exceptions into documented HTTP errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.completeness.exceptions import CompletenessError
from app.completeness.schemas import CompletenessReport, ErrorResponse
from app.completeness.services import CompletenessService
from app.database.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["completeness"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by both endpoints.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application not found."},
    500: {"model": ErrorResponse, "description": "Invalid document configuration or unexpected failure."},
}


def _handle_completeness_errors(func):
    """Translate :class:`CompletenessError` into HTTP error responses.

    Keeps the error mapping inside the completeness module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CompletenessError as exc:
            logger.error(
                "Completeness error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> CompletenessService:
    """Build the completeness service bound to the request session."""
    return CompletenessService(db)


@router.get(
    "/applications/{application_id}/completeness",
    response_model=CompletenessReport,
    summary="Get completeness report",
    description=(
        "Returns the current completeness report for an application, computed "
        "from its uploaded document metadata."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_completeness_errors
def get_completeness(
    application_id: int,
    db: _GET_DB,
) -> CompletenessReport:
    """Return the current completeness report for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The computed completeness report.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).get_report(application_id=application_id)


@router.post(
    "/applications/{application_id}/completeness/verify",
    response_model=CompletenessReport,
    summary="Verify document completeness",
    description=(
        "Runs completeness verification against the required/optional document "
        "catalogue and returns the freshly computed report."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_completeness_errors
def verify_completeness(
    application_id: int,
    db: _GET_DB,
) -> CompletenessReport:
    """Verify an application's document completeness.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The freshly computed completeness report.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).verify(application_id=application_id)
