"""Application configuration.

Centralizes all runtime configuration in a single, strongly typed
:class:`Settings` object loaded from environment variables and the ``.env``
file. Configuration values are validated by pydantic-settings at import time so
misconfiguration fails fast during application startup instead of at runtime.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "testing", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

#: Default connection string when ``DATABASE_URL`` is not provided. Development
#: only; production deployments must set an explicit ``DATABASE_URL``.
_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/finance_verification"
)

#: Default public prefix under which every API route is mounted.
DEFAULT_API_PREFIX = "/api/v1"

#: Default upload storage root: ``<project_root>/storage``. Files are kept
#: outside the source tree so they never leak into version control.
_DEFAULT_UPLOAD_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage"

#: Development-only secret placeholder. Long enough to satisfy the JWT minimum
#: key length (32 bytes); production deployments must override it.
_DEV_SECRET_KEY = "change-me-in-production-32-characters-minimum"


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables.

    Attributes:
        app_name: Human-readable application name.
        environment: Deployment environment (development, testing or
            production).
        debug: Enables debug behaviour (e.g. verbose error responses). Never
            enabled in production.
        secret_key: Secret used to sign tokens and derive cryptographic keys.
        database_url: SQLAlchemy database connection string.
        log_level: Root logging level.
        api_prefix: URL prefix applied to every API router.
        upload_storage_root: Root directory under which uploaded documents are
            stored on disk.
        max_upload_size_mb: Maximum accepted size for a single uploaded file.
        confidence_threshold: Field confidence below which a critical field
            forces human review (0.0 - 1.0).
        confidence_weights: Relative weight of every confidence source. Sources
            that did not contribute to a field are ignored and the remaining
            weights are renormalized automatically.
        access_token_expire_minutes: Lifetime of a signed access-token cookie.
        refresh_token_expire_days: Lifetime of a persisted refresh token when
            the user asked the device to be remembered.
        default_employee_id: Employee id seeded by the ``app.auth.seed``
            management script.
        default_employee_email: Email seeded by the ``app.auth.seed`` script.
        default_employee_name: Display name seeded by the seed script.
        default_employee_role: Role seeded by the seed script.
        default_employee_password: Password for the seeded default account.
        bulk_queue_workers: Number of controlled queue workers to run.
            Defaults to 1: PaddleOCREngine is a singleton shared across worker
            threads with no locking around `.predict()`, so concurrent workers
            can crash the process (SIGSEGV, PaddlePaddle/PaddleOCR#17787) --
            confirmed for real on 2026-08-19, not just a theoretical risk. Raise
            this only after adding a lock around the OCR call, or after moving
            OCR into a dedicated subprocess.
        bulk_queue_max_attempts: Default retry budget for one queue job.
        bulk_queue_poll_interval: Seconds workers wait between empty polls.
        bulk_queue_retry_backoff_seconds: Base seconds for exponential retry
            backoff (first retry waits ``1 * base``, then ``2 * base``, then
            ``4 * base``, ...).
        bulk_queue_stale_after_seconds: Seconds before a PROCESSING job with no
            worker heartbeat is treated as abandoned by a crashed worker.
        bulk_queue_background_drain: Whether the HTTP request lifecycle may run
            in-process workers after ``/processing/start`` and
            ``/processing/retry``. Production deployments that run dedicated
            worker processes (``python -m app.bulk_queue``) should disable this
            so queue draining never happens inside the request path.
        worker_heartbeat_path: File a dedicated worker process
            (``python -m app.bulk_queue``) touches periodically to prove it is
            alive; read by ``/health`` to detect a crashed or never-started
            worker process. Not written by the in-process background-drain
            mode, which has no persistent process for a heartbeat to describe.
        database_pool_size: Number of connections each database engine pool
            keeps open; bounds memory and file descriptors under load.
        database_max_overflow: Extra connections the pool may open on demand
            before clients queue for a free connection. The combined pool size
            is validated to be large enough for the configured queue workers.
        ai_fallback_enabled: Whether the analysis pipeline may consult an AI/VLM
            field fallback. AI stays a fallback, never the default: when
            enabled, only missing or invalid expected fields are sent to a
            configured fallback provider, and the rule/regex pipeline always
            runs first. Defaults to false (no AI calls ever).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="onboarding-automation-system")
    #: Fail closed: an omitted ``ENVIRONMENT`` must never silently enable
    #: development behaviour (non-Secure cookies, dev secret key, debug mode).
    #: Local development and CI set ``ENVIRONMENT`` explicitly (see
    #: ``backend/.env``/``.env.example`` and ``.github/workflows/ci.yml``), so
    #: the safe default is production.
    environment: Environment = Field(default="production")
    debug: bool = Field(default=False)
    secret_key: SecretStr = Field(default=SecretStr(_DEV_SECRET_KEY))
    database_url: str = Field(default=_DEFAULT_DATABASE_URL)
    log_level: LogLevel = Field(default="INFO")
    api_prefix: str = Field(default=DEFAULT_API_PREFIX)
    upload_storage_root: Path = Field(default=_DEFAULT_UPLOAD_STORAGE_ROOT)
    max_upload_size_mb: int = Field(default=25)
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    confidence_weights: dict[str, float] = Field(
        default={
            "regex": 0.50,
            "template": 0.30,
            "ocr": 0.20,
            "ai": 0.00,
        }
    )
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=30, ge=1)
    default_employee_id: str = Field(default="employee")
    default_employee_email: str = Field(default="employee@fintech.local")
    default_employee_name: str = Field(default="Employee")
    default_employee_role: str = Field(default="Verification Officer")
    default_employee_password: SecretStr = Field(
        default=SecretStr("12345678"),
    )
    default_operator_id: str = Field(default="operator")
    default_operator_email: str = Field(default="operator@fintech.local")
    default_operator_name: str = Field(default="Operator")
    default_operator_password: SecretStr = Field(
        default=SecretStr("12345678"),
    )
    default_reviewer_id: str = Field(default="reviewer")
    default_reviewer_email: str = Field(default="reviewer@fintech.local")
    default_reviewer_name: str = Field(default="Reviewer")
    default_reviewer_password: SecretStr = Field(
        default=SecretStr("12345678"),
    )
    default_it_id: str = Field(default="it")
    default_it_email: str = Field(default="it@fintech.local")
    default_it_name: str = Field(default="IT")
    default_it_password: SecretStr = Field(
        default=SecretStr("12345678"),
    )
    bulk_queue_workers: int = Field(default=1, ge=1, le=16)
    bulk_queue_max_attempts: int = Field(default=3, ge=1, le=10)
    bulk_queue_poll_interval: float = Field(default=1.0, ge=0.05, le=60.0)
    bulk_queue_retry_backoff_seconds: int = Field(default=30, ge=0)
    bulk_queue_stale_after_seconds: int = Field(default=900, ge=1)
    bulk_queue_background_drain: bool = Field(default=True)
    worker_heartbeat_path: Path = Field(default=Path("./worker.heartbeat"))
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    ai_fallback_enabled: bool = Field(default=False)

    @model_validator(mode="after")
    def _validate_environment(self) -> "Settings":
        """Guard against unsafe combinations for production deployments."""
        if self.environment == "production" and self.debug:
            raise ValueError("DEBUG must be false when ENVIRONMENT is production")
        if self.environment == "production" and self.secret_key.get_secret_value() == (
            _DEV_SECRET_KEY
        ):
            raise ValueError("SECRET_KEY must be overridden when ENVIRONMENT is production")
        if self.environment == "development":
            logging.getLogger(__name__).warning(
                "ENVIRONMENT is set to 'development' (default). "
                "Ensure ENVIRONMENT is set to 'production' in production deployments."
            )
        return self

    @model_validator(mode="after")
    def _validate_pool_sizing(self) -> "Settings":
        """Keep the database pool large enough for the configured queue workers.

        During an in-process drain every worker holds one claim session for the
        full duration of a job, plus a request session and occasional heartbeat
        sessions. A pool smaller than ``workers + 2`` would exhaust under load
        and fail claims; fail fast instead so operators size the pool.
        """
        total_pool = self.database_pool_size + self.database_max_overflow
        if total_pool < self.bulk_queue_workers + 2:
            raise ValueError(
                "DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW must be at least "
                "BULK_QUEUE_WORKERS + 2 so queue workers never exhaust "
                "database connections"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Caching keeps a single configuration object for the whole process and makes
    the factory suitable for dependency injection. The cache can be cleared in
    tests by calling ``get_settings.cache_clear()``.
    """
    return Settings()
