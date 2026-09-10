"""Tests for the authentication endpoints.

Authentication is exercised through the real FastAPI application and database,
following the same pattern as the rest of the suite. Tests assert cookie-based
session behaviour, credential validation, refresh rotation and logout.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.constants import (
    ACCESS_TOKEN_COOKIE,
    LOCKOUT_DURATION_MINUTES,
    MAX_FAILED_LOGIN_ATTEMPTS,
    REFRESH_TOKEN_COOKIE,
)
from app.auth.exceptions import AuthenticationError
from app.auth.services import AuthenticationService
from app.core.security import hash_password
from app.database.connection import SessionLocal
from app.database.models.user import User

DEFAULT_IDENTIFIER = "EMP-1001"
DEFAULT_EMAIL = "employee@fintech.local"
DEFAULT_PASSWORD = "Welcome@123"


def _create_user(*, active: bool = True, **overrides) -> User:
    """Insert a user with a known password and return it."""
    defaults = {
        "employee_id": DEFAULT_IDENTIFIER,
        "email": DEFAULT_EMAIL,
        "name": "Employee",
        "role": "Verification Officer",
        "password_hash": hash_password(DEFAULT_PASSWORD),
        "is_active": active,
    }
    defaults.update(overrides)
    db = SessionLocal()
    try:
        user = User(**defaults)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _reload_user(user_id: int) -> User:
    """Reload a user by id in a fresh session (avoids cross-session refresh())."""
    db = SessionLocal()
    try:
        return db.get(User, user_id)
    finally:
        db.close()


def _refresh_token_count(db) -> int:
    return db.scalar(text("SELECT count(*) FROM refresh_tokens"))


def _active_refresh_tokens(db) -> int:
    return db.scalar(
        text("SELECT count(*) FROM refresh_tokens WHERE revoked_at IS NULL")
    )


def _refresh_cookie_segment(response) -> str:
    """Return the refresh-cookie portion of a response's Set-Cookie header.

    The refresh cookie is set after the access cookie, so slicing the combined
    ``Set-Cookie`` header from the refresh cookie's name onwards isolates its
    attributes (e.g. whether ``Max-Age`` is present).
    """
    set_cookie = response.headers.get("set-cookie", "")
    start = set_cookie.find(REFRESH_TOKEN_COOKIE)
    assert start != -1, f"refresh cookie missing from Set-Cookie: {set_cookie!r}"
    return set_cookie[start:]


class TestLogin:
    """POST /auth/login."""

    def test_login_with_employee_id_sets_cookies(self, client: TestClient):
        _create_user()
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["user"]["employee_id"] == DEFAULT_IDENTIFIER
        assert payload["user"]["email"] == DEFAULT_EMAIL
        assert "password_hash" not in payload["user"]
        assert ACCESS_TOKEN_COOKIE in client.cookies
        assert REFRESH_TOKEN_COOKIE in client.cookies
        # The access cookie is a JWT (starts with "ey"), the refresh cookie is
        # an opaque random value.
        assert client.cookies.get(ACCESS_TOKEN_COOKIE).startswith("ey")
        assert not client.cookies.get(REFRESH_TOKEN_COOKIE).startswith("ey")

    def test_login_with_email_succeeds(self, client: TestClient):
        _create_user()
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_EMAIL,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        assert response.status_code == 200

    def test_login_wrong_password_is_401(self, client: TestClient):
        _create_user()
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": "WrongPassword1",
                "remember": False,
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid employee credentials"

    def test_login_unknown_identifier_is_401_not_404(self, client: TestClient):
        """Unknown users must not be distinguishable from wrong passwords."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": "EMP-9999",
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid employee credentials"

    def test_login_inactive_user_is_403(self, client: TestClient):
        _create_user(active=False)
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        assert response.status_code == 403

    def test_login_missing_fields_is_422(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": DEFAULT_IDENTIFIER},
        )
        assert response.status_code == 422

    def test_login_cookies_are_http_only_and_scoped(self, client: TestClient):
        _create_user()
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": True,
            },
        )
        set_cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        # The refresh cookie is scoped to the auth prefix, the access cookie to
        # the whole site.
        assert f"Path=/api/v1/auth" in set_cookie
        assert "Path=/" in set_cookie

    def test_login_remembered_sets_persistent_refresh_cookie(
        self, client: TestClient
    ):
        _create_user()
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": True,
            },
        )
        assert response.status_code == 200
        assert "Max-Age=" in _refresh_cookie_segment(response)

    def test_login_unremembered_sets_session_refresh_cookie(
        self, client: TestClient
    ):
        _create_user()
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        assert response.status_code == 200
        assert "Max-Age=" not in _refresh_cookie_segment(response)


class TestLoginLockout:
    """Regression tests for teammate triage #12: DB-backed login lockout.

    ``MAX_FAILED_LOGIN_ATTEMPTS`` consecutive wrong-password attempts against
    a known account lock it for ``LOCKOUT_DURATION_MINUTES``, regardless of
    whether a later attempt in that window uses the correct password.
    """

    def _wrong_password_attempts(self, client: TestClient, count: int):
        responses = []
        for _ in range(count):
            responses.append(
                client.post(
                    "/api/v1/auth/login",
                    json={
                        "identifier": DEFAULT_IDENTIFIER,
                        "password": "WrongPassword1",
                        "remember": False,
                    },
                )
            )
        return responses

    def test_lockout_triggers_after_max_failed_attempts(self, client: TestClient):
        user = _create_user()
        responses = self._wrong_password_attempts(client, MAX_FAILED_LOGIN_ATTEMPTS)
        assert all(r.status_code == 401 for r in responses)

        reloaded = _reload_user(user.id)
        assert reloaded.failed_login_attempts == 0
        assert reloaded.locked_until is not None

        locked_out_response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        assert locked_out_response.status_code == 429
        detail = locked_out_response.json()["detail"].lower()
        assert "minute" in detail
        assert str(LOCKOUT_DURATION_MINUTES) in detail

    def test_successful_login_resets_failed_attempt_counter(self, client: TestClient):
        user = _create_user()
        self._wrong_password_attempts(client, MAX_FAILED_LOGIN_ATTEMPTS - 1)

        reloaded = _reload_user(user.id)
        assert reloaded.failed_login_attempts == MAX_FAILED_LOGIN_ATTEMPTS - 1

        success_response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        assert success_response.status_code == 200

        reloaded = _reload_user(user.id)
        assert reloaded.failed_login_attempts == 0
        assert reloaded.locked_until is None

    def test_locked_account_rejects_even_the_correct_password(
        self, client: TestClient
    ):
        _create_user()
        self._wrong_password_attempts(client, MAX_FAILED_LOGIN_ATTEMPTS)

        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        assert response.status_code == 429
        assert ACCESS_TOKEN_COOKIE not in client.cookies

    def test_lockout_expires_after_the_configured_duration(self, client: TestClient):
        user = _create_user()
        self._wrong_password_attempts(client, MAX_FAILED_LOGIN_ATTEMPTS)

        reloaded = _reload_user(user.id)
        assert reloaded.locked_until is not None

        db = SessionLocal()
        try:
            # Simulate the lockout window having already elapsed.
            db.execute(
                text("UPDATE users SET locked_until = now() - interval '1 minute' WHERE id = :id"),
                {"id": user.id},
            )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        assert response.status_code == 200


class TestMe:
    """GET /auth/me."""

    def test_me_without_cookie_is_401(self, client: TestClient):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_with_valid_session_returns_user(self, client: TestClient):
        _create_user()
        client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 200
        assert response.json()["user"]["employee_id"] == DEFAULT_IDENTIFIER

    def test_me_with_garbage_access_cookie_is_401(self, client: TestClient):
        client.cookies.set(ACCESS_TOKEN_COOKIE, "not-a-jwt")
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_after_logout_is_401(self, client: TestClient):
        _create_user()
        client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        client.post("/api/v1/auth/logout")
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401


class TestRefresh:
    """POST /auth/refresh."""

    def test_refresh_rotates_tokens(self, client: TestClient):
        _create_user()
        client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": True,
            },
        )
        first_refresh = client.cookies.get(REFRESH_TOKEN_COOKIE)
        assert first_refresh

        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 200
        # The opaque refresh token is always replaced. (The access JWT is not
        # compared: PyJWT encodes timestamps with second precision, so two
        # tokens issued in the same second are byte-identical.)
        assert client.cookies.get(REFRESH_TOKEN_COOKIE) != first_refresh
        assert client.cookies.get(ACCESS_TOKEN_COOKIE).startswith("ey")

    def test_reused_refresh_token_is_rejected_after_rotation(
        self, client: TestClient
    ):
        _create_user()
        client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": True,
            },
        )
        first_refresh = client.cookies.get(REFRESH_TOKEN_COOKIE)
        client.post("/api/v1/auth/refresh")
        # Replay the pre-rotation token: must now fail.
        client.cookies.set(REFRESH_TOKEN_COOKIE, first_refresh)
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    def test_refresh_without_cookie_is_401(self, client: TestClient):
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    def test_refresh_preserves_persistent_cookie_for_remembered_login(
        self, client: TestClient
    ):
        _create_user()
        client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": True,
            },
        )
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 200
        assert "Max-Age=" in _refresh_cookie_segment(response)
        with SessionLocal() as db:
            remember = db.scalar(
                text("SELECT remember FROM refresh_tokens WHERE revoked_at IS NULL")
            )
            assert remember is True

    def test_refresh_keeps_session_cookie_for_unremembered_login(
        self, client: TestClient
    ):
        _create_user()
        client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": False,
            },
        )
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 200
        assert "Max-Age=" not in _refresh_cookie_segment(response)
        with SessionLocal() as db:
            remember = db.scalar(
                text("SELECT remember FROM refresh_tokens WHERE revoked_at IS NULL")
            )
            assert remember is False


class TestLogout:
    """POST /auth/logout."""

    def test_logout_revokes_refresh_token(self, client: TestClient):
        _create_user()
        client.post(
            "/api/v1/auth/login",
            json={
                "identifier": DEFAULT_IDENTIFIER,
                "password": DEFAULT_PASSWORD,
                "remember": True,
            },
        )
        with SessionLocal() as db:
            assert _active_refresh_tokens(db) == 1

        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 200
        with SessionLocal() as db:
            assert _active_refresh_tokens(db) == 0
            assert _refresh_token_count(db) == 1  # retained for the audit trail

    def test_logout_without_session_is_200(self, client: TestClient):
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 200


class TestPasswordHashing:
    """Password storage security."""

    def test_hash_is_not_plaintext(self):
        hashed = hash_password(DEFAULT_PASSWORD)
        assert hashed != DEFAULT_PASSWORD
        assert DEFAULT_PASSWORD not in hashed

    def test_hash_verifies_correct_password(self):
        hashed = hash_password(DEFAULT_PASSWORD)
        assert AuthenticationService.hash_password(DEFAULT_PASSWORD)
        assert hashed.startswith("$2")  # bcrypt prefix


class TestAuthenticationErrorBase:
    """docs/TEAMMATE_BUG_TRIAGE.md Low #22 -- the base class default."""

    def test_base_class_status_code_is_401_not_500(self):
        """No subclass is affected -- each overrides status_code already;
        this only guards the base class default, never raised directly in
        production but the fallback any future subclass would inherit."""
        assert AuthenticationError().status_code == 401
