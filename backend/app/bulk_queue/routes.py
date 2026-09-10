"""HTTP endpoints for the persistent bulk processing queue."""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.bulk_queue.exceptions import BulkQueueError
from app.bulk_queue.schemas import (
    EnqueueResponse,
    ErrorResponse,
    ProcessingActionResponse,
    ProcessingDocumentsResponse,
    ProcessingProgressResponse,
    QueueProgressResponse,
    QueueStatsResponse,
    WorkerRunResponse,
)
from app.bulk_queue.services import BulkQueueService
from app.bulk_queue.workers import drain_queue
from app.core.config import get_settings
from app.database.connection import get_db
from app.database.models.user import User
from app.database.repositories.queue_job_repository import QueueJobRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bulk-queue"])

_GET_DB = Annotated[Session, Depends(get_db)]
_CURRENT_USER = Annotated[User, Depends(get_current_user)]

_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application not found."},
    500: {"model": ErrorResponse, "description": "Queue operation failed."},
}


def _handle_queue_errors(func):
    """Translate queue exceptions into HTTP responses."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BulkQueueError as exc:
            logger.error("Bulk queue error %s: %s", exc.__class__.__name__, exc.detail)
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        except Exception as exc:
            logger.exception("Unexpected bulk queue failure: %s", exc.__class__.__name__)
            raise HTTPException(status_code=500, detail="Queue operation failed") from exc

    return wrapper


def _service(db: Session) -> BulkQueueService:
    return BulkQueueService(db)


def _run_processing_workers() -> None:
    """Run the configured workers outside the request session."""
    try:
        drain_queue()
    except Exception:
        logger.exception("Application document processing stopped unexpectedly")


def _schedule_drain(background_tasks: BackgroundTasks) -> None:
    """Schedule an in-process drain after the response, when enabled.

    Production deployments that run dedicated worker processes
    (``python -m app.bulk_queue``) set ``bulk_queue_background_drain=false`` so
    queue draining never happens inside the HTTP request path. The operator
    endpoints stay non-blocking in both modes: background draining runs after
    the response is sent, and dedicated worker processes poll independently.
    """
    if get_settings().bulk_queue_background_drain:
        background_tasks.add_task(_run_processing_workers)


@router.post(
    "/applications/{application_id}/processing/start",
    response_model=ProcessingActionResponse,
    summary="Start document processing",
    responses={401: {"model": ErrorResponse}, **_ERROR_RESPONSES},
)
@_handle_queue_errors
def start_processing(
    application_id: int,
    background_tasks: BackgroundTasks,
    db: _GET_DB,
    _user: _CURRENT_USER,
) -> ProcessingActionResponse:
    """Start processing uploaded documents for an authenticated operator."""
    response = _service(db).start_processing(application_id=application_id)
    if response.documents_queued or response.documents_already_in_progress:
        _schedule_drain(background_tasks)
    return response


@router.get(
    "/applications/{application_id}/processing/progress",
    response_model=ProcessingProgressResponse,
    summary="Get document processing progress",
    responses={401: {"model": ErrorResponse}, **_ERROR_RESPONSES},
)
@_handle_queue_errors
def processing_progress(
    application_id: int,
    db: _GET_DB,
    _user: _CURRENT_USER,
) -> ProcessingProgressResponse:
    """Return application-level document processing progress."""
    return _service(db).processing_progress(application_id=application_id)


@router.get(
    "/applications/{application_id}/processing/documents",
    response_model=ProcessingDocumentsResponse,
    summary="Get document processing statuses",
    responses={401: {"model": ErrorResponse}, **_ERROR_RESPONSES},
)
@_handle_queue_errors
def processing_documents(
    application_id: int,
    db: _GET_DB,
    _user: _CURRENT_USER,
) -> ProcessingDocumentsResponse:
    """Return safe per-document processing statuses."""
    return _service(db).processing_documents(application_id=application_id)


@router.post(
    "/applications/{application_id}/processing/retry",
    response_model=ProcessingActionResponse,
    summary="Retry documents needing attention",
    responses={401: {"model": ErrorResponse}, **_ERROR_RESPONSES},
)
@_handle_queue_errors
def retry_processing(
    application_id: int,
    background_tasks: BackgroundTasks,
    db: _GET_DB,
    _user: _CURRENT_USER,
) -> ProcessingActionResponse:
    """Retry failed documents without affecting unrelated documents."""
    response = _service(db).retry_failed(application_id=application_id)
    if response.documents_retried:
        _schedule_drain(background_tasks)
    return response


@router.post(
    "/applications/{application_id}/queue/enqueue",
    response_model=EnqueueResponse,
    summary="Enqueue uploaded documents",
    responses={401: {"model": ErrorResponse}, **_ERROR_RESPONSES},
)
@_handle_queue_errors
def enqueue_application(
    application_id: int,
    db: _GET_DB,
    _user: _CURRENT_USER,
) -> EnqueueResponse:
    """Enqueue all eligible UPLOADED documents for an application."""
    return _service(db).enqueue_application(application_id=application_id)


@router.get(
    "/applications/{application_id}/queue/progress",
    response_model=QueueProgressResponse,
    summary="Get queue progress",
    responses={401: {"model": ErrorResponse}, **_ERROR_RESPONSES},
)
@_handle_queue_errors
def queue_progress(
    application_id: int,
    db: _GET_DB,
    _user: _CURRENT_USER,
) -> QueueProgressResponse:
    """Return application-level queue progress."""
    return _service(db).progress(application_id=application_id)


@router.get(
    "/queue/stats",
    response_model=QueueStatsResponse,
    summary="Get system-wide queue backlog stats",
    responses={401: {"model": ErrorResponse}},
)
@_handle_queue_errors
def queue_stats(
    db: _GET_DB,
    _user: _CURRENT_USER,
) -> QueueStatsResponse:
    """Return operator-facing queue backlog counts across every application."""
    stats = QueueJobRepository(db).get_queue_stats()
    return QueueStatsResponse(
        total_queued=stats.total_queued,
        total_processing=stats.total_processing,
        total_failed=stats.total_failed,
        oldest_queued_age_seconds=stats.oldest_queued_age_seconds,
    )


@router.post(
    "/queue/workers/drain",
    response_model=WorkerRunResponse,
    summary="Drain available queue jobs",
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: _ERROR_RESPONSES[500]},
)
@_handle_queue_errors
def drain_workers(
    db: _GET_DB,
    _user: _CURRENT_USER,
    workers: Annotated[int | None, Query(ge=1, le=16)] = None,
) -> WorkerRunResponse:
    """Run controlled workers until the queue is empty.

    This operational endpoint is intentionally coarse-grained: it starts a
    bounded worker drain, never exposes internal errors, and relies on job
    progress endpoints for per-application visibility.
    """
    summary = drain_queue(workers=workers)
    resolved_workers = workers or get_settings().bulk_queue_workers
    return WorkerRunResponse(
        workers=resolved_workers,
        processed=summary.processed,
        succeeded=summary.succeeded,
        failed=summary.failed,
        retried=summary.retried,
    )
