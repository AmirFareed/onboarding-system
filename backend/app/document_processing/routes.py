"""HTTP endpoints for document processing.

Exposes the process (``POST``) and results (``GET``) endpoints. Routes stay thin:
they build the service per request and translate the module's domain exceptions
into documented HTTP errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.document_processing.exceptions import DocumentProcessingError
from app.document_processing.schemas import (
    ErrorResponse,
    OcrResultsResponse,
    ProcessDocumentsResponse,
)
from app.document_processing.services import DocumentProcessingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["document-processing"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by both endpoints.
_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Technical validation has not been run."},
    404: {"model": ErrorResponse, "description": "Application not found."},
    422: {"model": ErrorResponse, "description": "Document cannot be processed."},
    500: {"model": ErrorResponse, "description": "OCR processing failed."},
    504: {"model": ErrorResponse, "description": "Processing exceeded the time limit."},
}


def _handle_document_processing_errors(func):
    """Translate :class:`DocumentProcessingError` into HTTP error responses.

    Keeps the error mapping inside the document processing module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DocumentProcessingError as exc:
            logger.error(
                "Document processing error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> DocumentProcessingService:
    """Build the document processing service bound to the request session."""
    return DocumentProcessingService(db)


@router.post(
    "/applications/{application_id}/process-documents",
    response_model=ProcessDocumentsResponse,
    summary="Process all technically valid documents",
    description=(
        "Runs the document processing pipeline over every document of an "
        "application. Documents that did not pass technical validation are "
        "skipped; each processed document's raw text and extraction metrics are "
        "stored as its OCR result. Per-document failures are reported in the "
        "response and never abort the run."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_document_processing_errors
def process_documents(
    application_id: int,
    db: _GET_DB,
) -> ProcessDocumentsResponse:
    """Process every technically valid document of an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The outcome of the processing run for every document.

    Raises:
        HTTPException: When the application does not exist, technical validation
            has not run, or a document cannot be processed.
    """
    return _service(db).process(application_id=application_id)


@router.get(
    "/applications/{application_id}/ocr-results",
    response_model=OcrResultsResponse,
    summary="Get OCR results",
    description=(
        "Returns every stored OCR/text extraction result for an application's "
        "documents, including the raw text and extraction metrics."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_document_processing_errors
def get_ocr_results(
    application_id: int,
    db: _GET_DB,
) -> OcrResultsResponse:
    """Return every stored OCR/text extraction result for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The stored extraction results.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).get_results(application_id=application_id)
