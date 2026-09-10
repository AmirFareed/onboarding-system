"""System health endpoints.

Provides liveness and readiness information used by operators and infrastructure
(e.g. container health checks). The endpoints must never raise on transient
infrastructure failures; instead they report a degraded status so monitoring can
react without taking the application down.
"""

import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings, get_settings
from app.database.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

#: A heartbeat older than this many seconds is treated the same as a missing
#: one: whatever process last wrote it is no longer reliably alive.
_HEARTBEAT_STALE_AFTER_SECONDS = 60

_WORKER_HEARTBEAT_MESSAGE = "Queue worker heartbeat stale or missing"


def _worker_heartbeat_message(settings: Settings) -> str | None:
    """Return a problem message if the dedicated worker heartbeat is unhealthy.

    ``None`` means the heartbeat file exists and was refreshed recently.
    Any read failure (missing file, unreadable/corrupt contents) is treated
    the same as "stale": the check exists to answer "is a dedicated worker
    process alive", and any of those cases mean "not verifiably yes".
    """
    path = settings.worker_heartbeat_path
    try:
        written_at = float(path.read_text().strip())
    except (OSError, ValueError):
        return _WORKER_HEARTBEAT_MESSAGE
    if time.time() - written_at > _HEARTBEAT_STALE_AFTER_SECONDS:
        return _WORKER_HEARTBEAT_MESSAGE
    return None


@router.get(
    "/health",
    summary="Health check",
    description="Reports application liveness, database connectivity and queue worker liveness.",
)
def health_check(db: Session = Depends(get_db)) -> dict[str, object]:
    """Return the service health status.

    Verifies database connectivity with a trivial ``SELECT 1`` statement and
    checks the dedicated queue worker's heartbeat file. A database failure is
    reported as a ``degraded`` status rather than an HTTP error, because the
    application process itself remains available. A stale or missing worker
    heartbeat is reported as HTTP 200 with ``degraded: true`` rather than a
    top-level ``degraded`` status: the API itself is fully healthy, only
    queue processing may be stalled.

    Args:
        db: Active database session injected by FastAPI.

    Returns:
        A mapping describing service name, environment and health status.
    """
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Health check failed to reach the database")
        return {
            "status": "degraded",
            "service": settings.app_name,
            "environment": settings.environment,
            "version": __version__,
        }

    heartbeat_problem = _worker_heartbeat_message(settings)
    if heartbeat_problem is not None:
        return {
            "status": "ok",
            "degraded": True,
            "service": settings.app_name,
            "environment": settings.environment,
            "version": __version__,
            "details": {"worker": heartbeat_problem},
        }

    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": __version__,
    }
