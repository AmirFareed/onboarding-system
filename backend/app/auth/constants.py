"""Constants shared across the authentication module."""

#: Name of the HttpOnly cookie carrying the signed access token (JWT).
ACCESS_TOKEN_COOKIE = "fintech_access"

#: Name of the HttpOnly cookie carrying the opaque refresh token.
REFRESH_TOKEN_COOKIE = "fintech_refresh"

#: Cookie path restricting the refresh token to authentication endpoints.
#: The cookie is only transmitted on ``/api/v1/auth/*`` requests, shrinking the
#: surface area for accidental exposure.
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/auth"

#: Consecutive failed login attempts (for a known account) that trigger a
#: lockout. Resets to 0 on the next successful login.
MAX_FAILED_LOGIN_ATTEMPTS = 5

#: How long an account stays locked after hitting :data:`MAX_FAILED_LOGIN_ATTEMPTS`.
LOCKOUT_DURATION_MINUTES = 15
