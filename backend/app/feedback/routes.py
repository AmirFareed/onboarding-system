"""HTTP endpoints for the feedback module.

Exposes the feedback dataset over five read-only endpoints: a filtered and
paginated listing, a single entry lookup, deterministic aggregated statistics,
and JSON and CSV exports. Routes stay thin: they build the service per request
and translate the module's domain exceptions into documented HTTP errors.
"""

import logging
from datetime import datetime
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models.enums import DocumentType
from app.feedback.constants import DEFAULT_LIMIT, MAX_LIMIT
from app.feedback.exceptions import FeedbackError
from app.feedback.schemas import (
    ErrorResponse,
    ExportResponse,
    FeedbackEntry,
    FeedbackFilters,
    FeedbackStatistics,
    FeedbackSummary,
)
from app.feedback.services import FeedbackService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Feedback entry not found."},
    422: {"model": ErrorResponse, "description": "Invalid feedback filter."},
    500: {"model": ErrorResponse, "description": "Feedback operation failed."},
}


def _handle_feedback_errors(func):
    """Translate module errors into HTTP error responses.

    Keeps the error mapping inside the feedback module and compatible with
    FastAPI versions that do not expose router-level exception handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FeedbackError as exc:
            logger.error(
                "Feedback error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> FeedbackService:
    """Build the feedback service bound to the request session."""
    return FeedbackService(db)


def _feedback_filters(
    application_id: Annotated[int | None, Query(ge=1)] = None,
    reviewer: Annotated[str | None, Query(max_length=255)] = None,
    document_type: Annotated[DocumentType | None, Query()] = None,
    field_name: Annotated[str | None, Query(max_length=255)] = None,
    decision: Annotated[str | None, Query(max_length=50)] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
) -> FeedbackFilters:
    """Assemble the filter model from the query string."""
    return FeedbackFilters(
        application_id=application_id,
        reviewer=reviewer,
        document_type=document_type,
        field_name=field_name,
        decision=decision,
        date_from=date_from,
        date_to=date_to,
        min_confidence=min_confidence,
    )


@router.get(
    "/feedback",
    response_model=FeedbackSummary,
    summary="List feedback entries",
    description=(
        "Returns a paginated slice of the feedback dataset, newest first. "
        "Entries can be narrowed with the application, reviewer, document "
        "type, field name, decision, date range and minimum confidence "
        "filters."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_feedback_errors
def list_feedback(
    db: _GET_DB,
    filters: Annotated[FeedbackFilters, Depends(_feedback_filters)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> FeedbackSummary:
    """List feedback entries with filtering and pagination."""
    return _service(db).list_feedback(
        filters=filters,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/feedback/statistics",
    response_model=FeedbackStatistics,
    summary="Get feedback statistics",
    description=(
        "Aggregates the feedback dataset into deterministic statistics: total "
        "entries, corrected fields, most corrected fields, average confidence "
        "and distributions by reviewer, document type and decision, plus a "
        "daily correction frequency series. Optional filters narrow the "
        "population."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_feedback_errors
def get_feedback_statistics(
    db: _GET_DB,
    filters: Annotated[FeedbackFilters, Depends(_feedback_filters)],
) -> FeedbackStatistics:
    """Return aggregated statistics over the filtered dataset."""
    return _service(db).get_statistics(filters=filters)


@router.get(
    "/feedback/export/json",
    response_model=ExportResponse,
    summary="Export feedback as JSON",
    description=(
        "Exports the matching feedback population as a JSON array embedded in "
        "the response together with export metadata."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_feedback_errors
def export_feedback_json(
    db: _GET_DB,
    filters: Annotated[FeedbackFilters, Depends(_feedback_filters)],
) -> ExportResponse:
    """Export the filtered dataset as JSON."""
    return _service(db).export_json(filters=filters)


@router.get(
    "/feedback/export/csv",
    response_model=ExportResponse,
    summary="Export feedback as CSV",
    description=(
        "Exports the matching feedback population as CSV text embedded in the "
        "response together with export metadata."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_feedback_errors
def export_feedback_csv(
    db: _GET_DB,
    filters: Annotated[FeedbackFilters, Depends(_feedback_filters)],
) -> ExportResponse:
    """Export the filtered dataset as CSV."""
    return _service(db).export_csv(filters=filters)


@router.get(
    "/feedback/{feedback_id}",
    response_model=FeedbackEntry,
    summary="Get a feedback entry",
    description="Returns a single feedback entry by its dataset id.",
    responses=_ERROR_RESPONSES,
)
@_handle_feedback_errors
def get_feedback(
    feedback_id: int,
    db: _GET_DB,
) -> FeedbackEntry:
    """Return one feedback entry by id."""
    return _service(db).get_feedback(feedback_id=feedback_id)
