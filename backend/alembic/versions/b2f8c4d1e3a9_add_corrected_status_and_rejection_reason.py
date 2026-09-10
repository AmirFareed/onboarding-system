"""Add corrected application status and review rejection reason

Phase 12 final human verification: a CORRECT decision moves the application to
the new ``CORRECTED`` status, and a REJECT decision requires a mandatory
rejection reason stored on the review row, separate from the optional free-form
comments. Both changes are additive: the enum only gains a value (no existing
rows are affected) and ``human_reviews.rejection_reason`` is a nullable column.

Revision ID: b2f8c4d1e3a9
Revises: aa90cb91200c
Create Date: 2026-08-06

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2f8c4d1e3a9"
down_revision: Union[str, Sequence[str], None] = "aa90cb91200c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE applicationstatus ADD VALUE 'CORRECTED'")
    op.add_column(
        "human_reviews",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("human_reviews", "rejection_reason")
    op.execute(
        "UPDATE applications SET status = 'PENDING_REVIEW' "
        "WHERE status = 'CORRECTED'"
    )
    op.execute("ALTER TYPE applicationstatus DROP VALUE 'CORRECTED'")
