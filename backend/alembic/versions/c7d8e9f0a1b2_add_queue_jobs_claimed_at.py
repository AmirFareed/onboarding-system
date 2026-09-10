"""Add claimed_at column to queue_jobs

Adds ``claimed_at`` (nullable), a per-attempt claim timestamp that mirrors
``started_at`` at claim time but is never overwritten by the in-flight
liveness heartbeat (``QueueJobRepository.heartbeat``, which repeatedly
refreshes ``started_at`` so a live worker is never falsely declared
crashed). Because ``started_at`` drifts forward during a long-running job,
using it to measure elapsed processing time understates real duration --
confirmed on a real bulk-upload split job that ran ~46 minutes but reported
a small fraction of that. ``claimed_at`` gives the performance report
(``app/performance/services.py::_processing_spans``) a stable start bound.

Revision ID: c7d8e9f0a1b2
Revises: ae8554d98f13
Create Date: 2026-08-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'ae8554d98f13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "queue_jobs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("queue_jobs", "claimed_at")
