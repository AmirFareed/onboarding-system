"""add copy_number to documents

Adds the 1-based copy slot column to ``documents`` so an application can hold
multiple copies of a single document type (e.g. three 1-Link forms). Existing
rows default to copy 1, preserving the single-copy layout.

Revision ID: 9d7463779863
Revises: 0782434307bc
Create Date: 2026-08-11 12:20:55.983610

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9d7463779863'
down_revision: Union[str, Sequence[str], None] = '0782434307bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "documents",
        sa.Column(
            "copy_number",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_documents_app_type_copy",
        "documents",
        ["application_id", "document_type", "copy_number"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_documents_app_type_copy", table_name="documents")
    op.drop_column("documents", "copy_number")
