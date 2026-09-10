"""Add application display name

Adds a nullable ``name`` column to ``applications``. The name is a display
label derived from the first uploaded PDF filename (e.g. ``TMA Khal Dir
Lower`` for ``TMA Khal Dir Lower.pdf``), set automatically at upload time so
operators can scan/search for an application by the document they uploaded.
Existing rows keep ``NULL`` and fall back to the id/creator in the UI.

Revision ID: 7a1b2c3d4e5f
Revises: 02ffa030b9e1
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '02ffa030b9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("applications", sa.Column("name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("applications", "name")
