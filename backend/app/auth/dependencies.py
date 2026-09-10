"""FastAPI dependencies for authentication and role authorization."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.constants import ACCESS_TOKEN_COOKIE
from app.auth.repositories import UserRepository
from app.auth.roles import ROLE_EMPLOYEE, ROLES, effective_role
from app.auth.services import AuthenticationService
from app.core.config import get_settings
from app.database.connection import get_db
from app.database.models.user import User

_DB = Annotated[Session, Depends(get_db)]


def _dev_bypass_active() -> bool:
    """Whether the no-login, every-role-passes development bypass is on.

    Scoped strictly to ``ENVIRONMENT=development`` (this checkout's local
    ``.env``, never production or testing -- ``app.core.config.Settings``
    itself refuses the production combination of a dev secret/debug flag,
    and CI runs with ``ENVIRONMENT=testing``). Added 2026-09-03 at the
    user's explicit request to run the app locally without logging in and
    with every role's features reachable in one session, instead of
    switching between EMP-1001/OPR-1001/RVR-1001/IT-1001. Does not remove
    or weaken the real cookie/role system documented in CLAUDE.md as the
    actual security boundary -- it only short-circuits it while this one
    setting is on, exactly like the existing dev-only cookie/secret-key/
    seed-password relaxations already in this module's neighbors
    (app.core.security.py, app.auth.seed).
    """
    return get_settings().environment == "development"


def get_current_user(db: _DB, request: Request) -> User:
    """Resolve the authenticated user from the access-token cookie.

    In the development bypass (see :func:`_dev_bypass_active`), skips the
    cookie entirely and returns the real seeded EMPLOYEE account
    (``settings.default_employee_id``) so every downstream feature that
    records an actor (audit log, "created_by", ...) still has a real user
    row to point at -- not a synthetic in-memory object with no database
    identity.

    Raises a 401 (via the route error handler) when the cookie is missing,
    expired, invalid, or refers to a deactivated/removed user. In the
    development bypass, raises 401 instead when the default account has
    not been seeded yet (``python -m app.auth.seed``).

    Args:
        db: Active database session.
        request: Incoming request whose cookies are inspected.

    Returns:
        The authenticated user.
    """
    if _dev_bypass_active():
        user = UserRepository(db).get_by_employee_id(get_settings().default_employee_id)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Development login bypass is on but the default account "
                    "is not seeded. Run `python -m app.auth.seed`."
                ),
            )
        return user
    service = AuthenticationService(db)
    return service.get_user_by_access_token(request.cookies.get(ACCESS_TOKEN_COOKIE))


def require_role(*roles: str) -> Callable:
    """Build a FastAPI dependency requiring the user to hold any listed role.

    The dependency resolves the authenticated user via :func:`get_current_user`
    (so a missing/expired session still yields 401) and then enforces the role
    against the user's effective role (:func:`app.auth.roles.effective_role`,
    which normalizes legacy role strings). The all-access Employee role
    (:data:`app.auth.roles.ROLE_EMPLOYEE`) satisfies every guard by design. A
    user who holds none of the requested roles receives ``403 Forbidden``.

    Usage::

        @router.post("/...", dependencies=[Depends(require_role(ROLE_OPERATOR))])
        def handle(...): ...

    Args:
        *roles: Role strings the user must hold (any of them). Unrecognized
            role names are rejected at import time to catch typos.

    Returns:
        A FastAPI dependency callable yielding the authenticated user.
    """
    for role in roles:
        if role not in ROLES:
            raise ValueError(f"Unknown role requested: {role!r}")
    requested = frozenset(roles)

    def _require_role(current_user: User = Depends(get_current_user)) -> User:
        if _dev_bypass_active():
            return current_user
        effective = effective_role(current_user.role)
        if effective != ROLE_EMPLOYEE and effective not in requested:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _require_role


def require_exact_role(*roles: str) -> Callable:
    """Build a dependency requiring one of the listed roles exactly.

    Unlike :func:`require_role`, this guard does not let the all-access
    Employee role satisfy every request. Use it for features that are explicitly
    scoped to one operational role, such as IT-only reporting.
    """
    for role in roles:
        if role not in ROLES:
            raise ValueError(f"Unknown role requested: {role!r}")
    requested = frozenset(roles)

    def _require_exact_role(current_user: User = Depends(get_current_user)) -> User:
        if _dev_bypass_active():
            return current_user
        if effective_role(current_user.role) not in requested:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _require_exact_role
