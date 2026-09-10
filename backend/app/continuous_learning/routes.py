"""HTTP endpoints for the continuous learning module.

Exposes the curated learning dataset over five read-only endpoints: the full
curated dataset, its metadata, deterministic statistics and JSON and CSV
exports. Routes stay thin: they build the service per request and translate the
module's domain exceptions into documented HTTP errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.continuous_learning.exceptions import ContinuousLearningError
from app.continuous_learning.schemas import (
    DatasetMetadata,
    DatasetStatistics,
    ErrorResponse,
    ExportResponse,
    LearningDataset,
)
from app.continuous_learning.services import ContinuousLearningService
from app.database.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["continuous-learning"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Curated dataset is empty."},
    422: {"model": ErrorResponse, "description": "Curated dataset validation failed."},
    500: {"model": ErrorResponse, "description": "Continuous learning operation failed."},
}


def _handle_continuous_learning_errors(func):
    """Translate module errors into HTTP error responses.

    Keeps the error mapping inside the continuous learning module and compatible
    with FastAPI versions that do not expose router-level exception handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ContinuousLearningError as exc:
            logger.error(
                "Continuous learning error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc

    return wrapper


def _service(db: Session) -> ContinuousLearningService:
    """Build the continuous learning service bound to the request session."""
    return ContinuousLearningService(db)


@router.get(
    "/continuous-learning/dataset",
    response_model=LearningDataset,
    summary="Get curated learning dataset",
    description=(
        "Returns the curated, validated machine-learning dataset together with "
        "its reproducible metadata. Incomplete or invalid feedback samples are "
        "excluded; every record pairs the OCR value with the trusted "
        "human-corrected value."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_continuous_learning_errors
def get_learning_dataset(db: _GET_DB) -> LearningDataset:
    """Return the curated dataset with metadata."""
    return _service(db).get_dataset()


@router.get(
    "/continuous-learning/statistics",
    response_model=DatasetStatistics,
    summary="Get dataset statistics",
    description=(
        "Aggregates the curated dataset into deterministic statistics: total "
        "records, distributions by document type, field, decision, confidence "
        "bucket and reviewer, average confidence, dataset completeness and "
        "export metadata."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_continuous_learning_errors
def get_learning_statistics(db: _GET_DB) -> DatasetStatistics:
    """Return deterministic statistics over the curated dataset."""
    return _service(db).get_statistics()


@router.get(
    "/continuous-learning/export/json",
    response_model=ExportResponse,
    summary="Export curated dataset as JSON",
    description=(
        "Exports the curated dataset as a JSON array embedded in the response "
        "together with version, hash and export metadata."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_continuous_learning_errors
def export_learning_json(db: _GET_DB) -> ExportResponse:
    """Export the curated dataset as JSON."""
    return _service(db).export_json()


@router.get(
    "/continuous-learning/export/csv",
    response_model=ExportResponse,
    summary="Export curated dataset as CSV",
    description=(
        "Exports the curated dataset as CSV text embedded in the response "
        "together with version, hash and export metadata. The column order is "
        "the canonical 12-field record contract."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_continuous_learning_errors
def export_learning_csv(db: _GET_DB) -> ExportResponse:
    """Export the curated dataset as CSV."""
    return _service(db).export_csv()


@router.get(
    "/continuous-learning/version",
    response_model=DatasetMetadata,
    summary="Get dataset metadata",
    description=(
        "Returns the current dataset metadata: the deterministic version "
        "identifier, the SHA-256 content hash, the project version, the "
        "creation timestamp and the record count."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_continuous_learning_errors
def get_learning_version(db: _GET_DB) -> DatasetMetadata:
    """Return the current dataset metadata."""
    return _service(db).get_version()
