"""HTTP endpoints for technical file validation.

Exposes the read (``GET``) and run (``POST``) endpoints. The POST endpoint runs
technical validation for every uploaded document and returns the complete
report; the GET endpoint returns the stored reports from previous runs. Routes
stay thin and translate the module's domain exceptions into documented HTTP
errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.technical_validation.exceptions import TechnicalValidationError
from app.technical_validation.schemas import (
    ErrorResponse,
    TechnicalValidationListResponse,
)
from app.technical_validation.services import TechnicalValidationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["technical-validation"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by both endpoints.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application not found."},
    422: {
        "model": ErrorResponse,
        "description": "A document-level technical failure escaped the report.",
    },
    500: {"model": ErrorResponse, "description": "Unexpected validation failure."},
}


def _handle_technical_validation_errors(func):
    """Translate :class:`TechnicalValidationError` into HTTP error responses.

    Keeps the error mapping inside the technical validation module while
    remaining compatible with FastAPI versions that do not expose router-level
    exception handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TechnicalValidationError as exc:
            logger.error(
                "Technical validation error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> TechnicalValidationService:
    """Build the technical validation service bound to the request session."""
    return TechnicalValidationService(db)


@router.get(
    "/applications/{application_id}/technical-validation",
    response_model=TechnicalValidationListResponse,
    summary="List technical validation reports",
    description=(
        "Returns every stored technical validation report for an application, "
        "reconstructed from the persisted per-check results."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_technical_validation_errors
def get_technical_validation(
    application_id: int,
    db: _GET_DB,
) -> TechnicalValidationListResponse:
    """Return the stored technical validation reports for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The stored reports, newest run first per document.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).get_reports(application_id=application_id)


@router.post(
    "/applications/{application_id}/technical-validation/validate",
    response_model=TechnicalValidationListResponse,
    summary="Run technical validation",
    description=(
        "Runs technical validation for every uploaded document of the "
        "application: accessibility, file type, PDF/image structure, blur, "
        "rotation and readability. Returns the complete report and persists "
        "one check result per validation check."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_technical_validation_errors
def run_technical_validation(
    application_id: int,
    db: _GET_DB,
) -> TechnicalValidationListResponse:
    """Run technical validation for every document of an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The freshly generated technical validation reports.

    Raises:
        HTTPException: When the application does not exist or the run fails.
    """
    return _service(db).validate(application_id=application_id)
