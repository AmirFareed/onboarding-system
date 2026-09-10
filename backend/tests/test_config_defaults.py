"""Regression tests for the ENVIRONMENT default and its production guards.

The configuration must fail closed: an omitted ``ENVIRONMENT`` defaults to
production (with the existing production safety guards active) so a deployment
can never silently run with development behaviour. These tests construct
``Settings`` without the ``.env`` file (``_env_file=None``) and control
``ENVIRONMENT`` explicitly so they do not depend on where pytest is invoked
from.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import cookie_secure_enabled

#: A plausible non-development secret key, long enough to satisfy the JWT
#: minimum (32 bytes) without colliding with the development placeholder.
_REAL_SECRET_KEY = "a-real-production-secret-key-0123456789abcdef"


def _settings_without_dotenv(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Build Settings ignoring ``.env`` and any ambient ENVIRONMENT value."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    # A valid secret key is required once the default resolves to production.
    monkeypatch.setenv("SECRET_KEY", _REAL_SECRET_KEY)
    return Settings(_env_file=None)


def test_environment_defaults_to_production_when_omitted(monkeypatch):
    """Omitting ENVIRONMENT must not silently enable development behaviour."""
    settings = _settings_without_dotenv(monkeypatch)
    assert settings.environment == "production"


def test_production_with_development_secret_key_is_rejected(monkeypatch):
    """A production boot with the dev secret key must fail loudly."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="SECRET_KEY must be overridden"):
        Settings(_env_file=None)


def test_production_with_debug_enabled_is_rejected(monkeypatch):
    """A production boot with DEBUG enabled must fail loudly."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("SECRET_KEY", _REAL_SECRET_KEY)
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        Settings(_env_file=None)


def test_production_with_safe_config_is_accepted(monkeypatch):
    """A correctly configured production boot is valid and marks cookies Secure."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", _REAL_SECRET_KEY)
    settings = Settings(_env_file=None)
    assert settings.environment == "production"
    assert cookie_secure_enabled(settings) is True


def test_development_environment_is_still_accepted(monkeypatch):
    """Explicit development configuration remains valid (and cookies non-Secure)."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert cookie_secure_enabled(settings) is False