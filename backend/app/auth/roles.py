"""Operational role definitions and membership helpers.

Roles are stored on ``users.role`` as a free-form string (the existing schema
has no role enum). This module is the single source of truth for the three
operational roles and for mapping legacy role strings onto them so existing
accounts keep working while new role-specific behavior is enforced.

Role hierarchy for authorization:

- EMPLOYEE: the seeded default account (``Verification Officer``) and, by
  design, the all-access role: it is authorized for every operational role
  guard (operator, reviewer and IT actions) so the full application can be
  exercised with one account. This mirrors the product requirement that the
  Employee account can do everything.
- OPERATOR: first-level document/completeness checker. Requests missing
  documents, rejects incomplete applications, submits complete applications
  for processing. Never sees OCR/normalization/technical internals and cannot
  correct extracted fields.
- REVIEWER: second-level verification. Opens applications and documents,
  inspects extracted/normalized values, runs the human-verification workflow,
  approves/corrects/rejects.
- IT: technical/administrative. Reads system logs and operational audit
  information inside the IT settings area. Does not automatically gain
  business approval/review permissions.

Legacy role strings are normalized through :data:`ROLE_GROUPS` so
:func:`effective_role` always returns one of the canonical roles.
"""

from __future__ import annotations

ROLE_EMPLOYEE = "EMPLOYEE"
ROLE_OPERATOR = "OPERATOR"
ROLE_REVIEWER = "REVIEWER"
ROLE_IT = "IT"

#: Canonical roles a user can hold.
ROLES = frozenset({ROLE_EMPLOYEE, ROLE_OPERATOR, ROLE_REVIEWER, ROLE_IT})

#: Legacy role strings mapped to the canonical role they imply. The seeded
#: default account historically used ``Verification Officer`` and is the
#: all-access Employee account, so it maps to EMPLOYEE.
ROLE_GROUPS: dict[str, str] = {
    "Verification Officer": ROLE_EMPLOYEE,
}


def effective_role(role: str | None) -> str:
    """Return the canonical role for a stored role string.

    Args:
        role: Stored ``users.role`` value, if any.

    Returns:
        The canonical role: ``EMPLOYEE``, ``OPERATOR``, ``REVIEWER``, ``IT``,
        or the original string when it is not a recognized legacy value.
    """
    if not role:
        return ROLE_OPERATOR
    if role in ROLES:
        return role
    return ROLE_GROUPS.get(role, role)


def is_employee(user) -> bool:
    """Return whether the user holds the all-access Employee role."""
    return effective_role(getattr(user, "role", None)) == ROLE_EMPLOYEE


def is_operator(user) -> bool:
    """Return whether the user holds the operator role."""
    return effective_role(getattr(user, "role", None)) == ROLE_OPERATOR


def is_reviewer(user) -> bool:
    """Return whether the user holds the reviewer role."""
    return effective_role(getattr(user, "role", None)) == ROLE_REVIEWER


def is_it(user) -> bool:
    """Return whether the user holds the IT role."""
    return effective_role(getattr(user, "role", None)) == ROLE_IT