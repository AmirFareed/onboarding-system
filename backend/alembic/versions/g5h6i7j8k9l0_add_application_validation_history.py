"""Add application validation history table

Introduces ``application_validation_history``, an append-only record of the
operator/reviewer validation workflow: documents requested, documents received,
operator submissions and rejections, processing failures and final review
decisions. Each row records the actor, the status before/after, the missing
documents at that point and any comment, so repeated document submissions
preserve their full history instead of overwriting earlier records.

The ``validationeventtype`` enum mirrors ``app.database.models.enums``.

Revision ID: g5h6i7j8k9l0
Revises: f4a5b6c7d8e9
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'g5h6i7j8k9l0'
down_revision: Union[str, Sequence[str], None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    validationeventtype = sa.Enum(
        'DOCUMENTS_REQUESTED', 'DOCUMENTS_RECEIVED', 'OPERATOR_SUBMITTED',
        'OPERATOR_REJECTED', 'SUBMITTED_FOR_PROCESSING', 'PROCESSING_FAILED',
        'REVIEW_APPROVED', 'REVIEW_CORRECTED', 'REVIEW_REJECTED',
        name='validationeventtype',
    )

    op.create_table(
        'application_validation_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('event_type', validationeventtype, server_default=sa.text("'DOCUMENTS_REQUESTED'"), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_name', sa.String(length=255), nullable=True),
        sa.Column('actor_role', sa.String(length=100), nullable=True),
        sa.Column('previous_status', postgresql.ENUM('SUBMITTED', 'PROCESSING', 'PROCESSING_FAILED', 'PENDING_REVIEW', 'NEEDS_DOCUMENTS', 'APPROVED', 'REJECTED', 'CORRECTED', name='applicationstatus', create_type=False), nullable=True),
        sa.Column('new_status', postgresql.ENUM('SUBMITTED', 'PROCESSING', 'PROCESSING_FAILED', 'PENDING_REVIEW', 'NEEDS_DOCUMENTS', 'APPROVED', 'REJECTED', 'CORRECTED', name='applicationstatus', create_type=False), nullable=True),
        sa.Column('missing_document_types', sa.JSON(), nullable=True),
        sa.Column('document_ids', sa.JSON(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], name=op.f('fk_application_validation_history_applications_application_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_application_validation_history_users_actor_id'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_application_validation_history')),
    )
    op.create_index(
        'ix_application_validation_history_application_created',
        'application_validation_history',
        ['application_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_application_validation_history_application_created',
        table_name='application_validation_history',
    )
    op.drop_table('application_validation_history')
    sa.Enum(name='validationeventtype').drop(op.get_bind(), checkfirst=True)