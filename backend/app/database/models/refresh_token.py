"""Refresh token model.

Append-only record of issued refresh tokens. Tokens are stored as SHA-256
hashes so a database leak never exposes a usable token, and rotation is
enforced by revoking the previous token whenever a new one is issued. Logged
out tokens are revoked rather than deleted to preserve the audit trail.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User


class RefreshToken(Base):
    """A single issued refresh token.

    Attributes:
        id: Auto-incrementing primary key.
        user_id: Owner of the token.
        token_hash: SHA-256 digest of the opaque token value.
        expires_at: When the token can no longer be used (UTC).
        revoked_at: When the token was revoked, or ``None`` while active.
        remember: Whether the device should be remembered across browser
            restarts; carried across rotation so the refresh cookie keeps the
            login-time persistence choice.
        created_at: When the token was issued (UTC).
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remember: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RefreshToken id={self.id} user_id={self.user_id}>"
