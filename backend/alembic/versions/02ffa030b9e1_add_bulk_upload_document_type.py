"""Add BULK_UPLOAD document type

Adds the ``BULK_UPLOAD`` value to the ``documenttype`` Postgres enum. The
async bulk-upload flow (``UploadService.upload_bulk``) persists the
not-yet-split combined PDF as a ``Document`` row with this type before
enqueuing the background splitter job -- the Python ``DocumentType`` enum has
carried this value since the bulk-upload endpoint was added, but no migration
ever added it to the database enum, so every bulk upload raised
``InvalidTextRepresentation`` at insert time.

Revision ID: 02ffa030b9e1
Revises: 817ba7b6300b
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '02ffa030b9e1'
down_revision: Union[str, Sequence[str], None] = '817ba7b6300b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE documenttype ADD VALUE 'BULK_UPLOAD'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TYPE documenttype DROP VALUE 'BULK_UPLOAD'")
