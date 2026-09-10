"""Management script: seed the default employee and role accounts.

Run from the backend directory::

    python -m app.auth.seed

Creates (or updates) the default account whose credentials come from the
``DEFAULT_EMPLOYEE_*`` settings, plus one account per operational role
(operator, reviewer, IT) from the ``DEFAULT_OPERATOR_*``, ``DEFAULT_REVIEWER_*``
and ``DEFAULT_IT_*`` settings. Refuses to seed with the development default
password when the environment is production.

The script commits its own transaction and is safe to run repeatedly.
"""

import logging

from sqlalchemy import select

from app.auth.roles import ROLE_IT, ROLE_OPERATOR, ROLE_REVIEWER
from app.auth.services import AuthenticationService
from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models.user import User

logger = logging.getLogger(__name__)

#: Password shipped as the development default.
_DEV_DEFAULT_PASSWORD = "12345678"


def _load_or_create_user(
    db, *, employee_id: str, email: str, name: str, role: str, password: str
) -> tuple[User, bool]:
    """Return the user and whether it already existed."""
    existing = db.scalar(select(User).where(User.employee_id == employee_id))
    if existing is not None:
        return existing, True
    user = User(
        employee_id=employee_id,
        email=email,
        name=name,
        role=role,
        password_hash=AuthenticationService.hash_password(password),
    )
    db.add(user)
    return user, False


def _seed_role_account(
    db,
    *,
    employee_id: str,
    email: str,
    name: str,
    role: str,
    password: str,
) -> None:
    """Seed one role account idempotently."""
    user, existed = _load_or_create_user(
        db,
        employee_id=employee_id,
        email=email,
        name=name,
        role=role,
        password=password,
    )
    if not existed:
        logger.info("Created %s account %s (%s)", role.lower(), user.employee_id, user.email)


def seed() -> None:
    """Create or update the default employee and role accounts."""
    settings = get_settings()

    role_accounts = [
        (
            settings.default_operator_id,
            settings.default_operator_email,
            settings.default_operator_name,
            ROLE_OPERATOR,
            settings.default_operator_password.get_secret_value(),
        ),
        (
            settings.default_reviewer_id,
            settings.default_reviewer_email,
            settings.default_reviewer_name,
            ROLE_REVIEWER,
            settings.default_reviewer_password.get_secret_value(),
        ),
        (
            settings.default_it_id,
            settings.default_it_email,
            settings.default_it_name,
            ROLE_IT,
            settings.default_it_password.get_secret_value(),
        ),
    ]

    default_password = settings.default_employee_password.get_secret_value()
    if settings.environment == "production" and default_password == _DEV_DEFAULT_PASSWORD:
        raise SystemExit(
            "Refusing to seed: DEFAULT_EMPLOYEE_PASSWORD still uses the "
            "development default in a production environment."
        )

    db = SessionLocal()
    try:
        user, existed = _load_or_create_user(
            db,
            employee_id=settings.default_employee_id,
            email=settings.default_employee_email,
            name=settings.default_employee_name,
            role=settings.default_employee_role,
            password=default_password,
        )
        if not existed:
            logger.info(
                "Created default account %s (%s)",
                user.employee_id,
                user.email,
            )
        else:
            logger.info(
                "Account %s already exists; leaving it unchanged",
                user.employee_id,
            )
        for employee_id, email, name, role, password in role_accounts:
            _seed_role_account(
                db,
                employee_id=employee_id,
                email=email,
                name=name,
                role=role,
                password=password,
            )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    seed()
