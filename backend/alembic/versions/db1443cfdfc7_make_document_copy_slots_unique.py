"""make document copy slots unique

Converts the ``(application_id, document_type, copy_number)`` index on
``documents`` into a UNIQUE index so a numbered copy slot can hold exactly one
file per application. Enforced at the database level to back up the service-side
slot checks (duplicate bulk-upload splits, concurrent uploads, etc.).

Revision ID: db1443cfdfc7
Revises: 1b81ff3e40cd
Create Date: 2026-08-12 12:56:13.440076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db1443cfdfc7'
down_revision: Union[str, Sequence[str], None] = '1b81ff3e40cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_documents_app_type_copy", table_name="documents")
    op.create_index(
        "ix_documents_app_type_copy",
        "documents",
        ["application_id", "document_type", "copy_number"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_documents_app_type_copy", table_name="documents")
    op.create_index(
        "ix_documents_app_type_copy",
        "documents",
        ["application_id", "document_type", "copy_number"],
        unique=False,
    )
