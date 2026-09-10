"""add cnic document types

Adds the ``CNIC_FRONT`` and ``CNIC_BACK`` values to the ``documenttype``
Postgres enum so the upload pipeline accepts a CNIC front/back pair per
application.

Revision ID: 1b81ff3e40cd
Revises: 9d7463779863
Create Date: 2026-08-11 13:03:28.063759

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1b81ff3e40cd'
down_revision: Union[str, Sequence[str], None] = '9d7463779863'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE documenttype ADD VALUE 'CNIC_FRONT'")
    op.execute("ALTER TYPE documenttype ADD VALUE 'CNIC_BACK'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TYPE documenttype DROP VALUE 'CNIC_FRONT'")
    op.execute("ALTER TYPE documenttype DROP VALUE 'CNIC_BACK'")
