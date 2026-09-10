"""HTTP endpoints for document analysis.

Exposes the analyse (``POST``) and results (``GET``) endpoints. Routes stay thin:
they build the service per request and translate the module's domain exceptions
into documented HTTP errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.document_analysis.exceptions import DocumentAnalysisError
from app.document_analysis.schemas import (
    AnalysisResultsResponse,
    AnalyzeDocumentsResponse,
    ErrorResponse,
)
from app.document_analysis.services import DocumentAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["document-analysis"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by both endpoints.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application or OCR result not found."},
    422: {"model": ErrorResponse, "description": "Document type could not be determined."},
    500: {"model": ErrorResponse, "description": "Document analysis failed."},
}


def _handle_document_analysis_errors(func):
    """Translate :class:`DocumentAnalysisError` into HTTP error responses.

    Keeps the error mapping inside the document analysis module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DocumentAnalysisError as exc:
            logger.error(
                "Document analysis error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> DocumentAnalysisService:
    """Build the document analysis service bound to the request session."""
    return DocumentAnalysisService(db)


@router.post(
    "/applications/{application_id}/analyze-documents",
    response_model=AnalyzeDocumentsResponse,
    summary="Analyze all processed documents",
    description=(
        "Runs the document analysis pipeline over every document of an "
        "application: loads each OCR result, detects the analysed document "
        "type, extracts structured fields, validates them, runs cross-field "
        "consistency checks and computes a confidence score and verification "
        "status. Results are persisted; per-document failures (e.g. no OCR "
        "result) are reported in the response and never abort the run."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_document_analysis_errors
def analyze_documents(
    application_id: int,
    db: _GET_DB,
) -> AnalyzeDocumentsResponse:
    """Analyze every processed document of an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The outcome of the analysis run for every document.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).analyze(application_id=application_id)


@router.get(
    "/applications/{application_id}/analysis-results",
    response_model=AnalysisResultsResponse,
    summary="Get analysis results",
    description=(
        "Returns every stored analysis result for an application's documents, "
        "including the verification status, confidence score, extracted fields "
        "and issues."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_document_analysis_errors
def get_analysis_results(
    application_id: int,
    db: _GET_DB,
) -> AnalysisResultsResponse:
    """Return every stored analysis result for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The stored analysis results.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).get_results(application_id=application_id)
