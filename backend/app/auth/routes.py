"""HTTP endpoints for authentication.

Exposes the login, session, refresh and logout endpoints. Routes stay thin: the
service computes the token pair, the routes translate it into HttpOnly cookies
and translate module exceptions into documented HTTP errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.auth.constants import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE_PATH,
)
from app.auth.dependencies import get_current_user
from app.auth.exceptions import AuthenticationError
from app.auth.schemas import AuthResponse, LoginRequest
from app.auth.services import AuthenticationService
from app.core.config import Settings, get_settings
from app.core.security import cookie_secure_enabled
from app.database.connection import get_db
from app.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])

_GET_DB = Annotated[Session, Depends(get_db)]


def _handle_auth_errors(func):
    """Translate :class:`AuthenticationError` into HTTP error responses."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AuthenticationError as exc:
            logger.info(
                "Authentication error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> AuthenticationService:
    """Build the authentication service bound to the request session."""
    return AuthenticationService(db)


def _set_access_cookie(response: Response, token: str, settings: Settings) -> None:
    """Set the access-token cookie with a short-lived, HttpOnly JWT."""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        secure=cookie_secure_enabled(settings),
        httponly=True,
        samesite="lax",
    )


def _set_refresh_cookie(
    response: Response,
    token: str,
    settings: Settings,
    *,
    remember: bool,
) -> None:
    """Set the refresh-token cookie scoped to auth endpoints.

    ``remember`` controls whether the cookie persists across browser restarts;
    a session cookie is used otherwise.
    """
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60 if remember else None,
        path=REFRESH_TOKEN_COOKIE_PATH,
        secure=cookie_secure_enabled(settings),
        httponly=True,
        samesite="lax",
    )


def _clear_cookies(response: Response, settings: Settings) -> None:
    """Expire both auth cookies so no credential survives the response."""
    response.delete_cookie(
        ACCESS_TOKEN_COOKIE,
        path="/",
    )
    response.delete_cookie(
        REFRESH_TOKEN_COOKIE,
        path=REFRESH_TOKEN_COOKIE_PATH,
    )


@router.post(
    "/auth/login",
    response_model=AuthResponse,
    summary="Sign in",
    description=(
        "Authenticates an employee with their employee id or email and password, "
        "then issues short-lived access and refresh cookies. The access cookie is "
        "valid for minutes; the refresh cookie lasts for days when the device is "
        "remembered."
    ),
    responses={
        401: {"description": "Invalid employee credentials."},
        403: {"description": "The account has been deactivated."},
    },
)
@_handle_auth_errors
def login(
    payload: LoginRequest,
    response: Response,
    db: _GET_DB,
) -> AuthResponse:
    """Authenticate the user and set the session cookies.

    Args:
        payload: Identifier, password and remember flag.
        response: Response used to attach the session cookies.
        db: Active database session.

    Returns:
        The authenticated user.

    Raises:
        HTTPException: When the credentials are invalid or the account is
            deactivated.
    """
    settings = get_settings()
    service = _service(db)
    token_pair = service.login(
        identifier=payload.identifier,
        password=payload.password,
        remember=payload.remember,
    )
    user = service.get_user_by_access_token(token_pair.access_token)
    _set_access_cookie(response, token_pair.access_token, settings)
    _set_refresh_cookie(
        response,
        token_pair.refresh_token,
        settings,
        remember=payload.remember,
    )
    return AuthResponse(user=user)


@router.get(
    "/auth/me",
    response_model=AuthResponse,
    summary="Get current session",
    description="Returns the user identified by the access-token cookie.",
    responses={
        401: {"description": "Missing, expired or invalid session."},
    },
)
@_handle_auth_errors
def me(current_user: User = Depends(get_current_user)) -> AuthResponse:
    """Return the user behind the current access token.

    Delegates to the shared :func:`app.auth.dependencies.get_current_user`
    dependency (previously duplicated the cookie lookup inline) so this
    endpoint honors the same development no-login bypass as every other
    route instead of being the one place still requiring a real cookie.

    Args:
        current_user: The resolved user (cookie-based normally; the seeded
            EMPLOYEE account in the development bypass).

    Returns:
        The authenticated user.

    Raises:
        HTTPException: When there is no valid session.
    """
    return AuthResponse(user=current_user)


@router.post(
    "/auth/refresh",
    response_model=AuthResponse,
    summary="Refresh session",
    description=(
        "Rotates the refresh cookie into a fresh access token and a new refresh "
        "token. The previous refresh token is revoked server-side so it cannot be "
        "replayed."
    ),
    responses={
        401: {"description": "The refresh token is missing, expired or revoked."},
    },
)
@_handle_auth_errors
def refresh(request: Request, response: Response, db: _GET_DB) -> AuthResponse:
    """Rotate the refresh token and re-issue both cookies.

    Args:
        request: Incoming request carrying the refresh cookie.
        response: Response used to update the session cookies.
        db: Active database session.

    Returns:
        The authenticated user.

    Raises:
        HTTPException: When the refresh token is not acceptable.
    """
    settings = get_settings()
    token_pair = _service(db).refresh(
        request.cookies.get(REFRESH_TOKEN_COOKIE) or ""
    )
    user = _service(db).get_user_by_access_token(token_pair.access_token)
    _set_access_cookie(response, token_pair.access_token, settings)
    _set_refresh_cookie(response, token_pair.refresh_token, settings, remember=token_pair.remember)
    return AuthResponse(user=user)


@router.post(
    "/auth/logout",
    summary="Sign out",
    description=(
        "Revokes the refresh token and clears both cookies. Always succeeds so a "
        "sign-out is never blocked by an already-expired session."
    ),
)
@_handle_auth_errors
def logout(request: Request, response: Response, db: _GET_DB) -> dict[str, str]:
    """End the current session.

    Args:
        request: Incoming request carrying the refresh cookie.
        response: Response used to clear the session cookies.
        db: Active database session.

    Returns:
        A small confirmation payload.
    """
    settings = get_settings()
    _service(db).logout(request.cookies.get(REFRESH_TOKEN_COOKIE))
    _clear_cookies(response, settings)
    return {"detail": "Signed out"}
