"""Shared fixtures for the upload test suite.

Uploads are exercised through the real FastAPI application. The database is a
**dedicated test database** (``TEST_DATABASE_URL``, or the development database
name suffixed ``_test``): the ``DATABASE_URL`` environment variable is pointed
at it *before any application module is imported*, so the SQLAlchemy engine and
session factory built at import time bind to the test database -- never the
live development database that the running backend and queue worker use. A
session-scoped autouse fixture recreates the test database schema from scratch
(``alembic upgrade head``) once per run.

The storage backend is redirected to a per-test temporary directory so the
repository's ``storage/`` tree is never touched. The database is wiped before
and after every test via the cascade on ``applications`` (which removes
documents, OCR data, validations and reviews); ``_wipe_database`` additionally
refuses to run at all against a database whose name doesn't contain "test", as
a second, independent guard against ever wiping the real development database.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Point the application engine at a dedicated test database BEFORE any app
# module is imported. ``app.database.connection`` builds its engine and session
# factory at import time from ``DATABASE_URL``, so this must run before the
# ``from app...`` imports below.
#
# The development URL is read from the same ``.env`` file the application uses
# (``os.environ`` does not contain it unless it was exported), and the test URL
# is derived by appending ``_test`` to the database name. A caller can override
# either side explicitly via ``TEST_DATABASE_URL``.
# ---------------------------------------------------------------------------


def _dotenv_database_url() -> str:
    """Read DATABASE_URL from the backend's .env file, if present."""
    dotenv = Path(__file__).resolve().parent.parent / ".env"
    if not dotenv.is_file():
        return ""
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


_DOTENV_DATABASE_URL = _dotenv_database_url()
_TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", _DOTENV_DATABASE_URL).rsplit("/", 1)[0]
    + "/finance_verification_test",
)
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
# Pin the environment explicitly (matching CI) instead of relying on the
# ``.env`` file's ``development`` value or the production default. Tests are
# deterministic no matter which directory pytest runs from, and never inherit
# the unsafe "omitted ENVIRONMENT" case that ``config.py`` now fails closed on.
os.environ["ENVIRONMENT"] = "testing"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.auth.seed import seed as seed_default_account  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database.connection import SessionLocal  # noqa: E402
from app.database.models.user import User  # noqa: E402
from app.main import app  # noqa: E402

#: Credentials for the fixed operator identity the ``authenticated_client``
#: fixture logs in as. Safe to hardcode: ``isolated_database`` wipes every
#: user before and after each test, so there is never a collision with a
#: prior test's data.
_TEST_OPERATOR_EMPLOYEE_ID = "TEST-OPERATOR"
_TEST_OPERATOR_PASSWORD = "TestPass@123"

#: Minimal but realistic PDF payload starting with the ``%PDF-`` magic bytes.
PDF_BYTES = (
    b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)

#: PNG payload starting with the PNG signature.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
)

#: JPEG payload starting with the JPEG magic bytes.
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def _wipe_database() -> None:
    """Delete every application and user; dependent tables cascade."""
    db = SessionLocal()
    try:
        db_name = (db.get_bind().url.database or "").lower()
        if "test" not in db_name:
            raise RuntimeError(
                f"Refusing to wipe database {db_name!r} -- it does not look like "
                "a test database (name must contain 'test'). There is currently "
                "no isolated test database wired in; tests run directly against "
                "DATABASE_URL, which normally points at the real development "
                "database. See the 2026-08-13/2026-08-20 incidents in memory/"
                "CONTEXT.md this guard exists to prevent."
            )
        db.execute(text("DELETE FROM refresh_tokens"))
        db.execute(text("DELETE FROM audit_logs"))
        db.execute(text("DELETE FROM application_validation_history"))
        db.execute(text("DELETE FROM users"))
        db.execute(text("DELETE FROM applications"))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def storage_root(tmp_path: Path) -> Path:
    """A fresh, empty storage root for the test."""
    return tmp_path / "storage"


@pytest.fixture()
def client(storage_root: Path, monkeypatch: pytest.MonkeyPatch):
    """A TestClient whose upload service writes to the temporary storage root.

    The cached settings object is mutated in place (and restored afterwards) so
    every ``UploadService`` instantiated during the test resolves the temporary
    root, while the database settings remain the real development database.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_storage_root", storage_root)
    monkeypatch.setattr("app.upload.services.get_settings", lambda: settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def authenticated_client(client: TestClient) -> TestClient:
    """A ``client`` pre-authenticated as a fixed test operator identity.

    Every route except ``/health`` and the ``auth`` module itself requires a
    valid session (see ``app/api/__init__.py``). Tests that exercise those
    endpoints and aren't specifically testing the unauthenticated case should
    depend on this fixture instead of the raw ``client`` one -- it returns the
    same ``TestClient``, just with a valid session cookie already set, so
    every subsequent request on it carries the cookie automatically.
    """
    return _login_as(
        client,
        _TEST_OPERATOR_EMPLOYEE_ID,
        _TEST_OPERATOR_PASSWORD,
        name="Test Operator",
        role="Verification Officer",
    )


def _login_as(
    client: TestClient,
    employee_id: str,
    password: str,
    *,
    name: str,
    role: str,
) -> TestClient:
    """Create a user, log it in, and return the cookie-carrying client."""
    db = SessionLocal()
    try:
        db.add(
            User(
                employee_id=employee_id,
                email=f"{employee_id.lower()}@example.test",
                name=name,
                role=role,
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()
    response = client.post(
        f"{get_settings().api_prefix}/auth/login",
        json={
            "identifier": employee_id,
            "password": password,
            "remember": False,
        },
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture()
def operator_client(client: TestClient) -> TestClient:
    """A ``client`` logged in as an OPERATOR-role user.

    Roles are stored as free-form strings, so this fixture creates a user whose
    stored role is the canonical ``OPERATOR`` string, which
    :func:`app.auth.roles.effective_role` returns unchanged.
    """
    return _login_as_role(client, "OPERATOR", "TEST-OPERATOR")


@pytest.fixture()
def reviewer_client(client: TestClient) -> TestClient:
    """A ``client`` logged in as a REVIEWER-role user (canonical string)."""
    return _login_as_role(client, "REVIEWER", "TEST-REVIEWER")


@pytest.fixture()
def it_client(client: TestClient) -> TestClient:
    """A ``client`` logged in as an IT-role user (canonical string)."""
    return _login_as_role(client, "IT", "TEST-IT")


@pytest.fixture()
def employee_client(client: TestClient) -> TestClient:
    """A ``client`` logged in as the Employee all-access account."""
    return _login_as_role(client, "EMPLOYEE", "TEST-EMPLOYEE")


def _login_as_role(client: TestClient, role: str, employee_id: str) -> TestClient:
    """Create a user with a specific stored role and log it in."""
    return _login_as(
        client,
        employee_id,
        _TEST_OPERATOR_PASSWORD,
        name=f"Test {role}",
        role=role,
    )


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Create and migrate the dedicated test database once per session.

    Runs before any test: (1) connects to the server and creates the ``*_test``
    database if it does not exist, then (2) applies all Alembic migrations to it
    so its schema matches ``alembic upgrade head``. This is what lets
    ``isolated_database`` wipe tables before/after every test with zero risk to
    the live development database.

    The database role needs the ``CREATEDB`` privilege. On this machine the
    application role (``finance_app``) was created without it, so the test
    database must be created once by an administrator:

        CREATE DATABASE finance_verification_test OWNER finance_app;

    until then, this fixture raises with instructions rather than silently
    falling back to the development database.
    """
    _create_test_database_if_missing()
    _migrate_test_database()
    yield


def _server_superuser_url() -> str:
    """Return the test URL rewritten to the maintenance ``postgres`` database.

    Postgres cannot run ``CREATE DATABASE`` from inside a transaction and the
    target database may not exist yet, so the creation connection must attach
    to a database that always exists. Same credentials, database swapped.
    """
    from sqlalchemy.engine import make_url

    url = make_url(_TEST_DATABASE_URL)
    return url.set(database="postgres")


def _create_test_database_if_missing() -> None:
    """Create the dedicated test database when it does not exist."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    url = make_url(_TEST_DATABASE_URL)
    try:
        engine = create_engine(_server_superuser_url(), isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": url.database},
                ).scalar()
                if not exists:
                    conn.execute(text(f'CREATE DATABASE "{url.database}"'))
        finally:
            engine.dispose()
    except Exception as exc:  # pragma: no cover - environment provisioning
        if "InsufficientPrivilege" in str(exc):
            raise RuntimeError(
                "Cannot create the test database "
                f'"{url.database}": the application role lacks CREATEDB. '
                "Create it once as a database administrator, e.g.\n\n"
                "    CREATE DATABASE finance_verification_test OWNER finance_app;\n\n"
                "or point TEST_DATABASE_URL at a pre-created database."
            ) from exc
        raise


def _migrate_test_database() -> None:
    """Apply every Alembic migration to the test database (``upgrade head``)."""
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def isolated_database():
    """Guarantee a clean database around every test."""
    _wipe_database()
    yield
    _wipe_database()


@pytest.fixture(scope="session", autouse=True)
def restore_default_account():
    """Re-create the default employee account once the whole session has run.

    ``isolated_database`` wipes every user around each test, which also removes
    the seeded ``DEFAULT_EMPLOYEE_*`` account that development and manual login
    depend on. Re-seeding afterwards keeps the local environment usable after a
    test run.
    """
    yield
    seed_default_account()
