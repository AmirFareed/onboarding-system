"""Align document enums with the Phase 3 upload module.

The ``documenttype`` enum is rebuilt with the canonical Phase 3 document
categories and the ``documentprocessingstatus`` enum gains the ``UPLOADED``
state assigned to every freshly uploaded document.

The ``documents`` table is empty at migration time, so the document type values
can be replaced freely (rebuild the enum type and cast the column text value).
The processing status only gains a value, which PostgreSQL permits without a
column rewrite.

Revision ID: d1f7c4a9e2b3
Revises: 7ea33639f2a2
Create Date: 2026-08-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1f7c4a9e2b3"
down_revision: str | None = "7ea33639f2a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Canonical Phase 3 document categories (order preserved from the enum).
DOCUMENT_TYPE_VALUES = (
    "TRIPARTITE_AGREEMENT",
    "BILATERAL_AGREEMENT",
    "ACCOUNT_MAINTENANCE_CERTIFICATE",
    "ONE_LINK_LETTER",
    "AUTHORITY_LETTER",
    "SCHEDULE_OF_CHARGES",
    "BUSINESS_REQUIREMENT_DOCUMENT",
    "FORMAL_REQUEST_LETTER",
    "OTHER_SUPPORTING_DOCUMENT",
)

#: Phase 2 document categories that are replaced by ``DOCUMENT_TYPE_VALUES``.
LEGACY_DOCUMENT_TYPE_VALUES = (
    "AUTHORITY_LETTER",
    "ACCOUNT_MAINTENANCE",
    "ONELINK",
    "TRIPARTITE",
    "SCHEDULE_OF_CHARGES",
    "BUSINESS_REQUIREMENT",
    "FORMAL_REQUEST",
    "BANK_STATEMENT",
    "OTHER",
)


def upgrade() -> None:
    op.execute("ALTER TYPE documenttype RENAME TO documenttype_legacy")
    document_type_enum = sa.Enum(*DOCUMENT_TYPE_VALUES, name="documenttype")
    document_type_enum.create(op.get_bind(), checkfirst=True)
    op.execute(
        "ALTER TABLE documents ALTER COLUMN document_type "
        "TYPE documenttype USING document_type::text::documenttype"
    )
    op.execute("DROP TYPE documenttype_legacy")

    op.execute("ALTER TYPE documentprocessingstatus ADD VALUE 'UPLOADED'")


def downgrade() -> None:
    op.execute(
        "UPDATE documents SET processing_status = 'PENDING' "
        "WHERE processing_status = 'UPLOADED'"
    )
    op.execute("ALTER TYPE documentprocessingstatus DROP VALUE 'UPLOADED'")

    legacy_enum = sa.Enum(*LEGACY_DOCUMENT_TYPE_VALUES, name="documenttype_legacy")
    op.execute("ALTER TYPE documenttype RENAME TO documenttype_new")
    legacy_enum.create(op.get_bind(), checkfirst=True)
    op.execute(
        "ALTER TABLE documents ALTER COLUMN document_type "
        "TYPE documenttype_legacy USING document_type::text::documenttype_legacy"
    )
    op.execute("DROP TYPE documenttype_new")
    op.execute("ALTER TYPE documenttype_legacy RENAME TO documenttype")
