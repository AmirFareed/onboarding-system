"""Add document_id to human_corrections.

Two documents on the same application can extract a same-named field
(e.g. "account_number" on a bank statement and again on a payslip). The
review endpoint now accepts a document_id per correction to disambiguate
which document's field is being corrected; this column lets the persisted
audit record (and the review-history read model) preserve that same
distinction instead of only ever recording the field name. Nullable and
SET NULL on document delete, matching the existing
feedback_dataset.document_id convention -- existing rows have no document_id
and don't need a backfill, since they predate a feature that didn't exist
when they were written.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-14 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "human_corrections",
        sa.Column("document_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_human_corrections_document_id",
        "human_corrections",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_human_corrections_document_id",
        "human_corrections",
        ["document_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_human_corrections_document_id", table_name="human_corrections")
    op.drop_constraint(
        "fk_human_corrections_document_id", "human_corrections", type_="foreignkey"
    )
    op.drop_column("human_corrections", "document_id")
