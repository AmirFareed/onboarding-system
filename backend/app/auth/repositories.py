"""Persistence operations for the authentication entities."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.refresh_token import RefreshToken
from app.database.models.user import User
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Persistence operations for :class:`User`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[User]:
        return User

    def get_by_employee_id(self, employee_id: str) -> User | None:
        """Return the user with the given employee id, or ``None``.

        Args:
            employee_id: Unique employee identifier.

        Returns:
            The matching user or ``None``.
        """
        statement = select(User).where(User.employee_id == employee_id)
        return self._db.scalar(statement)

    def get_by_email(self, email: str) -> User | None:
        """Return the user with the given email, or ``None``.

        Args:
            email: Unique work email.

        Returns:
            The matching user or ``None``.
        """
        statement = select(User).where(User.email == email)
        return self._db.scalar(statement)

    def get_by_identifier(self, identifier: str) -> User | None:
        """Return the user matching an employee id or email, or ``None``.

        Args:
            identifier: Employee id or email entered on the login form.

        Returns:
            The matching user or ``None``.
        """
        return self.get_by_employee_id(identifier) or self.get_by_email(identifier)


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Persistence operations for :class:`RefreshToken`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[RefreshToken]:
        return RefreshToken

    def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        remember: bool = False,
    ) -> RefreshToken:
        """Persist a new refresh token record.

        Args:
            user_id: Owning user.
            token_hash: SHA-256 digest of the opaque token value.
            expires_at: Absolute expiry of the token.
            remember: Whether the session persists across browser restarts.

        Returns:
            The persisted token record.
        """
        entry = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            remember=remember,
        )
        self._db.add(entry)
        return self._commit_and_refresh(entry)

    def get_active_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Return a non-revoked, non-expired token matching the hash.

        Args:
            token_hash: SHA-256 digest of the presented token.

        Returns:
            The matching active token or ``None``.
        """
        now = datetime.now(UTC)
        statement = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        return self._db.scalar(statement)

    def revoke(self, token: RefreshToken) -> RefreshToken:
        """Revoke a token and persist the change.

        Args:
            token: Token record to revoke.

        Returns:
            The revoked token record.
        """
        token.revoked_at = datetime.now(UTC)
        return self._commit_and_refresh(token)
