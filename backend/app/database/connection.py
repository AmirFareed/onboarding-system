"""Database engine and session management.

Builds the synchronous SQLAlchemy engine from application settings and exposes a
session factory plus a FastAPI dependency that yields one session per request.
Sessions are always closed, even when an exception escapes the endpoint.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine configured for the given settings.

    ``pool_pre_ping`` verifies the connection is alive before handing it to the
    application, protecting against silently stale pooled connections after a
    database restart. Debug mode enables SQL echo for development inspection.
    The pool is bounded by ``database_pool_size`` / ``database_max_overflow`` so
    a large queue can never exhaust the database connection limit (and with it
    memory and file descriptors).

    Args:
        settings: Application settings providing the database URL.

    Returns:
        A configured :class:`sqlalchemy.engine.Engine`.
    """
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=settings.debug,
        future=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )


_settings = get_settings()
engine: Engine = create_engine_from_settings(_settings)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session.

    Yields a session from the local factory and guarantees it is closed once the
    request completes, including on unhandled exceptions.

    Yields:
        An active :class:`sqlalchemy.orm.Session` bound to the application
        engine.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
