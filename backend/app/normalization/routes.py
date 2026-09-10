"""HTTP endpoints for data normalization.

Exposes the normalize (``POST``) and normalized-fields (``GET``) endpoints.
Routes stay thin: they build the service per request and translate the module's
domain exceptions into documented HTTP errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.normalization.exceptions import NormalizationError
from app.normalization.schemas import (
    ErrorResponse,
    NormalizedFieldRecord,
    NormalizeResponse,
)
from app.normalization.services import NormalizationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["normalization"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by both endpoints.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application not found."},
    422: {
        "model": ErrorResponse,
        "description": "No extracted fields found.",
    },
    500: {"model": ErrorResponse, "description": "Normalization failed."},
}


def _handle_normalization_errors(func):
    """Translate :class:`NormalizationError` into HTTP error responses.

    Keeps the error mapping inside the normalization module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NormalizationError as exc:
            logger.error(
                "Normalization error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> NormalizationService:
    """Build the normalization service bound to the request session."""
    return NormalizationService(db)


@router.post(
    "/applications/{application_id}/normalize",
    response_model=NormalizeResponse,
    summary="Normalize verified fields",
    description=(
        "Runs every verified extracted field of an application through its "
        "configured normalizer and stores the canonical form in the field's "
        "normalized value. Human-corrected values take precedence over "
        "extracted ones; unverified and empty fields are skipped. The "
        "application becomes ready for business validation."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_normalization_errors
def normalize_application(
    application_id: int,
    db: _GET_DB,
) -> NormalizeResponse:
    """Normalize an application's verified extracted fields.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The normalization outcome with per-field results and a summary.

    Raises:
        HTTPException: When the application does not exist or has no extracted
            fields.
    """
    return _service(db).normalize(application_id=application_id)


@router.get(
    "/applications/{application_id}/normalized-fields",
    response_model=list[NormalizedFieldRecord],
    summary="Get normalized fields",
    description=(
        "Returns every stored extracted field of an application together with "
        "its persisted normalized value, when normalization has run."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_normalization_errors
def get_normalized_fields(
    application_id: int,
    db: _GET_DB,
) -> list[NormalizedFieldRecord]:
    """Return an application's extracted fields and their canonical values.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The stored field records with normalized values.

    Raises:
        HTTPException: When the application does not exist or has no extracted
            fields.
    """
    return _service(db).get_normalized_fields(application_id=application_id)
