"""Extend audit logs for the IT system-log API

Adds structured, filterable columns to ``audit_logs`` so the IT-only system-log
endpoint can search by actor role, document, severity and status transitions
without parsing the free-form ``details`` JSON. All new columns are nullable so
existing rows (written before this migration) remain valid; the new operator
workflow and system-log readers populate them going forward.

Revision ID: h8i9j0k1l2m3
Revises: g5h6i7j8k9l0
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, Sequence[str], None] = 'g5h6i7j8k9l0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'audit_logs',
        sa.Column('actor_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'audit_logs',
        sa.Column('actor_role', sa.String(length=100), nullable=True),
    )
    op.add_column(
        'audit_logs',
        sa.Column('document_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'audit_logs',
        sa.Column('severity', sa.String(length=20), nullable=True),
    )
    op.add_column(
        'audit_logs',
        sa.Column('previous_status', sa.String(length=40), nullable=True),
    )
    op.add_column(
        'audit_logs',
        sa.Column('new_status', sa.String(length=40), nullable=True),
    )
    op.create_foreign_key(
        op.f('fk_audit_logs_users_actor_id'),
        'audit_logs',
        'users',
        ['actor_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        op.f('fk_audit_logs_documents_document_id'),
        'audit_logs',
        'documents',
        ['document_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_audit_logs_actor_role',
        'audit_logs',
        ['actor_role'],
        unique=False,
    )
    op.create_index(
        'ix_audit_logs_performed_at',
        'audit_logs',
        ['performed_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_audit_logs_performed_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor_role', table_name='audit_logs')
    op.drop_constraint(
        op.f('fk_audit_logs_documents_document_id'),
        'audit_logs',
        type_='foreignkey',
    )
    op.drop_constraint(
        op.f('fk_audit_logs_users_actor_id'),
        'audit_logs',
        type_='foreignkey',
    )
    op.drop_column('audit_logs', 'new_status')
    op.drop_column('audit_logs', 'previous_status')
    op.drop_column('audit_logs', 'severity')
    op.drop_column('audit_logs', 'document_id')
    op.drop_column('audit_logs', 'actor_role')
    op.drop_column('audit_logs', 'actor_id')