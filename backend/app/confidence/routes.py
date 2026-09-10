"""HTTP endpoints for confidence scoring and human verification.

Exposes the evaluate (``POST``) and review (``POST``) endpoints. Routes stay
thin: they build the service per request and translate the module's domain
exceptions into documented HTTP errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.confidence.exceptions import ConfidenceError
from app.confidence.schemas import (
    ErrorResponse,
    EvaluateResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.confidence.services import ConfidenceService
from app.database.connection import get_db
from app.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["confidence"])

_GET_DB = Annotated[Session, Depends(get_db)]
_CURRENT_USER = Annotated[User, Depends(get_current_user)]

#: Shared OpenAPI error-response documentation reused by both endpoints.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application not found."},
    409: {"model": ErrorResponse, "description": "Review already applied."},
    422: {
        "model": ErrorResponse,
        "description": (
            "No analysis results, review not required or invalid review payload."
        ),
    },
    500: {"model": ErrorResponse, "description": "Confidence scoring failed."},
}


def _handle_confidence_errors(func):
    """Translate :class:`ConfidenceError` into HTTP error responses.

    Keeps the error mapping inside the confidence module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ConfidenceError as exc:
            logger.error(
                "Confidence error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> ConfidenceService:
    """Build the confidence service bound to the request session."""
    return ConfidenceService(db)


@router.post(
    "/applications/{application_id}/confidence/evaluate",
    response_model=EvaluateResponse,
    summary="Evaluate field confidence",
    description=(
        "Scores every extracted field of an application's analyzed documents "
        "from the available confidence sources, persists the per-field result, "
        "and decides whether human review is required. A critical field below "
        "the configured threshold returns only the low-confidence fields for "
        "review; otherwise the application is ready for normalization."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_confidence_errors
def evaluate_confidence(
    application_id: int,
    db: _GET_DB,
) -> EvaluateResponse:
    """Evaluate an application's extracted field confidence.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The evaluation outcome.

    Raises:
        HTTPException: When the application does not exist or has no analyzed
            documents.
    """
    return _service(db).evaluate(application_id=application_id)


@router.post(
    "/applications/{application_id}/confidence/review",
    response_model=ReviewResponse,
    summary="Submit a human review",
    description=(
        "Applies the employee's decisions to the flagged low-confidence "
        "fields. Corrected fields update the extracted value and record a "
        "feedback-dataset sample. A 'cannot verify' decision halts processing "
        "and returns PROCESSING_HALTED; otherwise the application becomes ready "
        "for normalization."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_confidence_errors
def review_confidence(
    application_id: int,
    request: ReviewRequest,
    db: _GET_DB,
    current_user: _CURRENT_USER,
) -> ReviewResponse:
    """Submit a human review for an application's flagged fields.

    Args:
        application_id: Id of the application.
        request: Review payload with the employee's decisions.
        db: Active database session.
        current_user: The authenticated employee, recorded as the reviewer.

    Returns:
        The final processing status.

    Raises:
        HTTPException: When the application does not exist, no review is
            required, the review is already applied or the payload is invalid.
    """
    return _service(db).review(
        application_id=application_id,
        request=request,
        reviewer_name=current_user.name,
    )
