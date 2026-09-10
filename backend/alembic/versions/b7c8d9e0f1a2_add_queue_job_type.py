"""Add job_type to queue_jobs and make document_id nullable.

Adds a ``jobtype`` enum (``DOCUMENT_OCR``, ``APPLICATION_PIPELINE``) so the
persistent queue can carry a second kind of job -- one that runs the
post-OCR pipeline (analysis, confidence, normalization, rule validation) for
a whole application, rather than processing a single document. Existing rows
default to ``DOCUMENT_OCR`` so no backfill is needed. ``document_id`` becomes
nullable because ``APPLICATION_PIPELINE`` jobs act on the application as a
whole and carry no document. A partial unique index guarantees at most one
pipeline job per application even if two workers race to enqueue it.

Revision ID: b7c8d9e0f1a2
Revises: 7a1b2c3d4e5f
Create Date: 2026-08-14 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "7a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    job_type = postgresql.ENUM(
        "DOCUMENT_OCR",
        "APPLICATION_PIPELINE",
        name="jobtype",
        create_type=False,
    )
    job_type.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "queue_jobs",
        sa.Column(
            "job_type",
            job_type,
            server_default=sa.text("'DOCUMENT_OCR'"),
            nullable=False,
        ),
    )
    op.alter_column("queue_jobs", "document_id", existing_type=sa.Integer(), nullable=True)
    op.create_index(
        "uq_queue_jobs_application_pipeline",
        "queue_jobs",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("job_type = 'APPLICATION_PIPELINE'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_queue_jobs_application_pipeline", table_name="queue_jobs")
    op.alter_column("queue_jobs", "document_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("queue_jobs", "job_type")
    sa.Enum(name="jobtype").drop(op.get_bind(), checkfirst=True)
