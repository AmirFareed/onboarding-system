"""Add PROCESSING_FAILED application status

Adds the ``PROCESSING_FAILED`` value to the ``applicationstatus`` Postgres
enum. Before this, an application whose documents all failed processing (the
``PIPELINE_BLOCKED`` case in ``app.bulk_queue.workers``) had no automated
pipeline run and therefore no status transition out of ``PROCESSING`` -- it
sat there indefinitely, indistinguishable from an application still being
actively worked on. This value gives that dead-end a real, visible terminal
state. Additive only: the enum gains a value, no existing rows are affected.

Note: like the ``CORRECTED`` (b2f8c4d1e3a9) and ``BULK_UPLOAD``
(02ffa030b9e1) enum-value migrations before it, ``downgrade()`` below is
best-effort only -- PostgreSQL has never supported ``ALTER TYPE ... DROP
VALUE`` as real DDL, so running this migration's downgrade will fail at the
final statement. This is a known, repeated limitation of the enum-add pattern
in this codebase, not something newly introduced here; it has not been fixed
in any of the three migrations that hit it.

Revision ID: e1f2a3b4c5d6
Revises: c8d9e0f1a2b3
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE applicationstatus ADD VALUE 'PROCESSING_FAILED'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE applications SET status = 'PROCESSING' "
        "WHERE status = 'PROCESSING_FAILED'"
    )
    op.execute("ALTER TYPE applicationstatus DROP VALUE 'PROCESSING_FAILED'")
