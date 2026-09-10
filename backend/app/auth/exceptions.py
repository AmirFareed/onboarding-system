"""Custom exceptions raised by the authentication module.

Each exception carries an HTTP status code and a human-readable detail message,
mirroring the convention used across the other modules so the route layer can
translate any failure into a consistent, documented error response.
"""


class AuthenticationError(Exception):
    """Base class for every authentication module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 401
    detail: str = "Authentication failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class InvalidCredentials(AuthenticationError):
    """The supplied employee id/email or password does not match.

    Raised for both unknown identifiers and wrong passwords so callers cannot
    distinguish which part of the login failed (user enumeration guard).
    """

    status_code = 401
    detail = "Invalid employee credentials"


class AccountInactive(AuthenticationError):
    """The account exists but is disabled and cannot sign in."""

    status_code = 403
    detail = "This account has been deactivated"


class InvalidRefreshToken(AuthenticationError):
    """The refresh token is unknown, revoked or expired."""

    status_code = 401
    detail = "Your session has expired. Please sign in again"


class MissingCredentials(AuthenticationError):
    """No access token was supplied with a protected request."""

    status_code = 401
    detail = "Authentication required"


class UserNotFound(AuthenticationError):
    """The user referenced by a valid access token no longer exists."""

    status_code = 401
    detail = "Your session is no longer valid"


class AccountLocked(AuthenticationError):
    """Too many recent failed login attempts; the account is temporarily locked.

    The default ``detail`` is a fallback -- callers should normally pass a
    message stating how many minutes remain, since that's what makes the
    lockout actionable for the person seeing it.
    """

    status_code = 429
    detail = "Too many failed login attempts. Please try again later."
