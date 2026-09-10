"""Add login lockout columns to users

Adds ``failed_login_attempts`` (defaults to 0) and ``locked_until``
(nullable) to ``users``, backing a DB-persisted login lockout: 5
consecutive failed attempts locks the account for 15 minutes
(``app.auth.constants.MAX_FAILED_LOGIN_ATTEMPTS`` /
``LOCKOUT_DURATION_MINUTES``), checked and updated inside
``AuthenticationService.login()``. Teammate triage #12.

Revision ID: ae8554d98f13
Revises: 16ed21e96c574f0b
Create Date: 2026-08-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ae8554d98f13'
down_revision: Union[str, Sequence[str], None] = '16ed21e96c574f0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
