"""Merge multiple heads from branches

Revision ID: 817ba7b6300b
Revises: a3f9b7c1d4e2, e6a1b2c3d4f5
Create Date: 2026-08-13 14:14:32.714668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '817ba7b6300b'
down_revision: Union[str, Sequence[str], None] = ('a3f9b7c1d4e2', 'e6a1b2c3d4f5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
