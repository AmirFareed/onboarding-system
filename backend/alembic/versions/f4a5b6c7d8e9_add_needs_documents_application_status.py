"""Add NEEDS_DOCUMENTS application status

Adds the ``NEEDS_DOCUMENTS`` value to the ``applicationstatus`` Postgres enum.
An operator who finds a submitted application incomplete (or who reviews it and
decides more documents are required) moves it to this state; the application
returns to ``SUBMITTED``/``PROCESSING`` when the customer/business sends the
requested documents again. This gives the operator validation queue a real,
backend-enforced state instead of a purely frontend notion of "needs documents".

Additive only: the enum gains a value, no existing rows are affected.

Note: like the enum-value migrations before it (``CORRECTED`` in b2f8c4d1e3a9,
``PROCESSING_FAILED`` in e1f2a3b4c5d6), ``downgrade()`` below is best-effort
only -- PostgreSQL has never supported ``ALTER TYPE ... DROP VALUE`` as real
DDL, so running this migration's downgrade will fail at the final statement.
This is a known, repeated limitation of the enum-add pattern in this codebase.

Revision ID: f4a5b6c7d8e9
Revises: e1f2a3b4c5d6
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE applicationstatus ADD VALUE 'NEEDS_DOCUMENTS'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE applications SET status = 'SUBMITTED' "
        "WHERE status = 'NEEDS_DOCUMENTS'"
    )
    op.execute("ALTER TYPE applicationstatus DROP VALUE 'NEEDS_DOCUMENTS'")