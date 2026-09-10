"""
Conftest for document splitter tests.

These tests are self-contained and do not need a database or HTTP client.
pytest always imports every conftest.py from the rootdir down to a test's
directory, so the parent ``tests/conftest.py`` is loaded regardless of what
lives here — an empty file does not stop that. What it *does* stop is the
parent's autouse ``isolated_database``/``restore_default_account`` fixtures
from touching Postgres for tests in this directory: pytest resolves an
autouse fixture by name using the closest conftest.py, so redefining them
here as no-ops overrides the parent's DB-wiping versions for every test
under ``tests/preprocessing/``.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_database():
    """Override the parent's DB-wiping fixture: these tests touch no database."""
    yield


@pytest.fixture(scope="session", autouse=True)
def restore_default_account():
    """Override the parent's account-reseeding fixture: nothing here needs it."""
    yield
