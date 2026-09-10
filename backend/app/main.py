"""FastAPI application entry point.

Defines the application factory ``create_app`` and a module-level ``app``
instance used by the ASGI server (``uvicorn app.main:app``). The factory keeps
application construction explicit and makes it trivial to build configured app
instances for tests and command-line tooling.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api import api_router
from app.auth.exceptions import AuthenticationError
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.connection import engine

logger = logging.getLogger(__name__)

#: Tags documented in the OpenAPI schema and grouped in Swagger UI.
OPENAPI_TAGS = [
    {
        "name": "system",
        "description": "Health and operational endpoints.",
    },
    {
        "name": "authentication",
        "description": "Sign in, session, refresh and sign-out endpoints.",
    },
]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    Args:
        settings: Optional pre-built settings; defaults to the cached process
            settings. Passing settings explicitly enables dependency injection
            in tests.

    Returns:
        A fully configured :class:`fastapi.FastAPI` instance.
    """
    resolved_settings = settings or get_settings()
    configure_logging(level=resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        """Manage application resources for the process lifetime."""
        logger.info(
            "Starting %s (%s) in %s environment",
            resolved_settings.app_name,
            __version__,
            resolved_settings.environment,
        )
        try:
            yield
        finally:
            engine.dispose()
            logger.info("Database engine disposed; application shutting down")

    application = FastAPI(
        title=resolved_settings.app_name,
        description=(
            "Backend for the Onboarding Automation System. Provides "
            "the foundational API used by later phases for document upload, "
            "extraction and validation workflows."
        ),
        version=__version__,
        debug=resolved_settings.debug,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )

    @application.exception_handler(AuthenticationError)
    async def _auth_error_handler(request: Request, exc: AuthenticationError):
        """Translate auth errors into HTTP responses."""
        logger.info("Authentication error %s: %s", exc.__class__.__name__, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    application.include_router(api_router, prefix=resolved_settings.api_prefix)
    logger.info(
        "Registered API routers under prefix '%s'",
        resolved_settings.api_prefix,
    )
    return application


app = create_app()
