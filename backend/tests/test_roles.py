"""Tests for the role definition and membership helpers.

Roles are stored as free-form strings; ``app.auth.roles`` is the single source
of truth mapping legacy strings onto the three canonical operational roles.
"""

import pytest

from app.auth.roles import (
    ROLE_EMPLOYEE,
    ROLE_GROUPS,
    ROLE_IT,
    ROLES,
    ROLE_OPERATOR,
    ROLE_REVIEWER,
    effective_role,
    is_employee,
    is_it,
    is_operator,
    is_reviewer,
)


class _User:
    """Minimal stand-in exposing a ``role`` attribute."""

    def __init__(self, role: str | None):
        self.role = role


def test_canonical_roles_are_exactly_four():
    """The canonical roles are EMPLOYEE, OPERATOR, REVIEWER and IT."""
    assert ROLES == frozenset({ROLE_EMPLOYEE, ROLE_OPERATOR, ROLE_REVIEWER, ROLE_IT})


def test_effective_role_passthrough_for_canonical_roles():
    """Canonical role strings map to themselves."""
    for role in (ROLE_EMPLOYEE, ROLE_OPERATOR, ROLE_REVIEWER, ROLE_IT):
        assert effective_role(role) == role


def test_effective_role_maps_legacy_verification_officer():
    """The legacy 'Verification Officer' role maps to EMPLOYEE."""
    assert effective_role("Verification Officer") == ROLE_EMPLOYEE
    assert ROLE_GROUPS["Verification Officer"] == ROLE_EMPLOYEE


def test_effective_role_defaults_empty_to_operator():
    """A missing/empty role falls back to OPERATOR."""
    assert effective_role(None) == ROLE_OPERATOR
    assert effective_role("") == ROLE_OPERATOR


def test_effective_role_unknown_role_passes_through():
    """An unrecognized role string is returned unchanged."""
    assert effective_role("SOMETHING_ELSE") == "SOMETHING_ELSE"


def test_role_membership_helpers():
    """The is_* helpers test the effective role."""
    assert is_employee(_User("Verification Officer"))
    assert not is_employee(_User(ROLE_OPERATOR))
    assert is_operator(_User(ROLE_OPERATOR))
    assert not is_operator(_User(ROLE_REVIEWER))
    assert not is_reviewer(_User("Verification Officer"))
    assert is_reviewer(_User(ROLE_REVIEWER))
    assert not is_reviewer(_User(ROLE_OPERATOR))
    assert is_it(_User(ROLE_IT))
    assert not is_it(_User(ROLE_REVIEWER))
    assert is_operator(_User(None))


def test_require_role_rejects_unknown_roles():
    """Building a dependency for an unknown role raises immediately."""
    from app.auth.dependencies import require_role

    with pytest.raises(ValueError):
        require_role("NOT_A_ROLE")


def test_require_role_allows_employee_for_any_guard():
    """The all-access Employee account passes every role guard."""
    from fastapi import HTTPException

    from app.auth.dependencies import require_role

    for role in (ROLE_OPERATOR, ROLE_REVIEWER, ROLE_IT):
        dep = require_role(role)
        assert dep(_User("Verification Officer")) is not None

    with pytest.raises(HTTPException) as excinfo:
        require_role(ROLE_IT)(_User(ROLE_REVIEWER))
    assert excinfo.value.status_code == 403