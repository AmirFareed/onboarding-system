"""Security helpers.

Password hashing (bcrypt), JWT access-token signing/verification and opaque
refresh-token generation. Access tokens are stateless JWTs signed with the
application secret; refresh tokens are random values stored hashed in the
database so they can be revoked individually.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings, get_settings

#: Hash algorithm used to sign access tokens.
_JWT_ALGORITHM = "HS256"

#: Claim carrying the user id inside an access token.
USER_CLAIM = "uid"


class TokenDecodeError(Exception):
    """Raised when an access token is malformed, expired or signed incorrectly."""


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given password.

    Args:
        password: Plaintext password.

    Returns:
        The bcrypt hash as a UTF-8 string.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a bcrypt hash.

    Never raises on malformed hashes; a failed check returns ``False`` so callers
    can respond with a generic authentication error.

    Args:
        password: Plaintext password candidate.
        password_hash: Stored bcrypt hash.

    Returns:
        ``True`` when the password matches, ``False`` otherwise.
    """
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, *, expires_delta: timedelta) -> str:
    """Create a signed JWT access token carrying the user id.

    Args:
        user_id: Id of the authenticated user.
        expires_delta: Time-to-live for the token.

    Returns:
        A signed JWT string.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        USER_CLAIM: str(user_id),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=_JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> int:
    """Validate an access token and return the user id it identifies.

    Args:
        token: Encoded JWT access token.

    Returns:
        The user id stored in the token.

    Raises:
        TokenDecodeError: When the token is expired, malformed or was signed
            with a different secret.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[_JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise TokenDecodeError("Invalid access token") from exc
    try:
        return int(payload[USER_CLAIM])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenDecodeError("Access token is missing the user id") from exc


def generate_refresh_token() -> str:
    """Generate a cryptographically random opaque refresh token.

    Returns:
        A URL-safe random string.
    """
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Return the SHA-256 digest used to store a refresh token in the database.

    Args:
        token: Opaque token value.

    Returns:
        Hex digest of the token.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def cookie_secure_enabled(settings: Settings) -> bool:
    """Return whether cookies must carry the ``Secure`` flag.

    Cookies are marked secure in production. Development environments commonly
    serve over plain HTTP, so marking them secure there would break the login
    flow in local setups.

    Args:
        settings: Application settings.

    Returns:
        ``True`` when the environment is production.
    """
    return settings.environment == "production"
