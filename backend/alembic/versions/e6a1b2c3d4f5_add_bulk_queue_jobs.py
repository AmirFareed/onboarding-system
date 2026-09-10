"""Add persistent bulk processing queue jobs.

Revision ID: e6a1b2c3d4f5
Revises: db1443cfdfc7
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e6a1b2c3d4f5"
down_revision: Union[str, Sequence[str], None] = "db1443cfdfc7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    job_status = postgresql.ENUM(
        "QUEUED",
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "RETRY_WAITING",
        name="jobstatus",
        create_type=False,
    )
    job_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "queue_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("status", job_status, server_default=sa.text("'QUEUED'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_queue_jobs_application_id", "queue_jobs", ["application_id"], unique=False)
    op.create_index("ix_queue_jobs_retry_at", "queue_jobs", ["retry_at"], unique=False)
    op.create_index("ix_queue_jobs_status", "queue_jobs", ["status"], unique=False)
    op.create_index("uq_queue_jobs_document_id", "queue_jobs", ["document_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_queue_jobs_document_id", table_name="queue_jobs")
    op.drop_index("ix_queue_jobs_status", table_name="queue_jobs")
    op.drop_index("ix_queue_jobs_retry_at", table_name="queue_jobs")
    op.drop_index("ix_queue_jobs_application_id", table_name="queue_jobs")
    op.drop_table("queue_jobs")
    sa.Enum(name="jobstatus").drop(op.get_bind(), checkfirst=True)
