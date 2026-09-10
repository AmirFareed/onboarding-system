"""HTTP endpoints for the business rule engine.

Exposes the validate (``POST``) and validation-results (``GET``) endpoints.
Routes stay thin: they build the service per request and translate the module's
domain exceptions into documented HTTP errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.rule_engine.exceptions import RuleEngineError
from app.rule_engine.schemas import (
    ErrorResponse,
    RuleEngineResponse,
    ValidationResultsResponse,
)
from app.rule_engine.services import RuleEngineService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rule-engine"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by both endpoints.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application not found."},
    500: {"model": ErrorResponse, "description": "Business rule validation failed."},
}


def _handle_rule_engine_errors(func):
    """Translate :class:`RuleEngineError` into HTTP error responses.

    Keeps the error mapping inside the rule engine module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RuleEngineError as exc:
            logger.error(
                "Rule engine error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> RuleEngineService:
    """Build the rule engine service bound to the request session."""
    return RuleEngineService(db)


@router.post(
    "/applications/{application_id}/validate",
    response_model=RuleEngineResponse,
    summary="Validate application business rules",
    description=(
        "Runs every configured business rule against an application's "
        "normalized, verified evidence: required documents, critical field "
        "presence, field formats, cross-document consistency, dates and "
        "periods, visual signature/stamp verification, policy compliance and "
        "data quality. Each rule result is persisted and the run's overall "
        "status is the strictest failing outcome."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_rule_engine_errors
def validate_application(
    application_id: int,
    db: _GET_DB,
) -> RuleEngineResponse:
    """Validate an application against the business rules.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The validation outcome with per-rule results and summaries.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).validate(application_id=application_id)


@router.get(
    "/applications/{application_id}/validation-results",
    response_model=ValidationResultsResponse,
    summary="Get stored rule validation results",
    description=(
        "Returns the persisted outcomes of the latest business rule validation "
        "run for an application. Results can be filtered to a single rule "
        "category. Technical validation rows are never included."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_rule_engine_errors
def get_validation_results(
    application_id: int,
    db: _GET_DB,
    category: str | None = Query(
        default=None,
        description="Optional rule category to filter on.",
    ),
) -> ValidationResultsResponse:
    """Return an application's stored rule validation results.

    Args:
        application_id: Id of the application.
        db: Active database session.
        category: Optional category to filter on.

    Returns:
        The stored per-rule outcome rows.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).get_results(application_id=application_id, category=category)
