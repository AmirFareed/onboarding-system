"""Enrich feedback dataset with provenance and review metadata

Phase 13 feedback module: each feedback entry must expose the document, OCR
result, normalized value, confidence source, correction reason, reviewer,
decision and origin of the correction. These additive nullable columns are
populated at write time by the confidence scoring and final human verification
phases; this migration also backfills the rows that already exist so the
retrospective dataset is complete.

Existing rows are classified deterministically: any row whose application has a
final ``human_reviews`` row belongs to the final human review; every remaining
row was recorded by the low-confidence review. Document-level provenance is
resolved from the human-verified extracted field that matches the application
and field name (best effort, first match by id).

Revision ID: c3d5e6f7a1b2
Revises: b2f8c4d1e3a9
Create Date: 2026-08-06

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d5e6f7a1b2"
down_revision: Union[str, Sequence[str], None] = "b2f8c4d1e3a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "feedback_dataset",
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey(
                "documents.id",
                ondelete="SET NULL",
                name=op.f("fk_feedback_dataset_documents_document_id"),
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "feedback_dataset",
        sa.Column(
            "ocr_result_id",
            sa.Integer(),
            sa.ForeignKey(
                "ocr_results.id",
                ondelete="SET NULL",
                name=op.f("fk_feedback_dataset_ocr_results_ocr_result_id"),
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "feedback_dataset",
        sa.Column("normalized_value", sa.Text(), nullable=True),
    )
    op.add_column(
        "feedback_dataset",
        sa.Column("confidence_source", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "feedback_dataset",
        sa.Column("correction_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "feedback_dataset",
        sa.Column("reviewer", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "feedback_dataset",
        sa.Column("decision", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "feedback_dataset",
        sa.Column("origin", sa.String(length=50), nullable=True),
    )
    op.create_index(
        op.f("ix_feedback_dataset_document_id"),
        "feedback_dataset",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feedback_dataset_field_name"),
        "feedback_dataset",
        ["field_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feedback_dataset_reviewer"),
        "feedback_dataset",
        ["reviewer"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feedback_dataset_decision"),
        "feedback_dataset",
        ["decision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feedback_dataset_origin"),
        "feedback_dataset",
        ["origin"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feedback_dataset_recorded_at"),
        "feedback_dataset",
        ["recorded_at"],
        unique=False,
    )

    # -- Backfill document-level provenance from the human-verified field ----
    op.execute(
        """
        UPDATE feedback_dataset AS fd
        SET
            document_id = (
                SELECT d.id
                FROM extracted_fields AS ef
                JOIN ocr_results AS o ON o.id = ef.ocr_result_id
                JOIN documents AS d ON d.id = o.document_id
                WHERE d.application_id = fd.application_id
                  AND ef.field_name = fd.field_name
                  AND ef.human_verified = TRUE
                ORDER BY ef.id
                LIMIT 1
            ),
            ocr_result_id = (
                SELECT ef.ocr_result_id
                FROM extracted_fields AS ef
                JOIN ocr_results AS o ON o.id = ef.ocr_result_id
                JOIN documents AS d ON d.id = o.document_id
                WHERE d.application_id = fd.application_id
                  AND ef.field_name = fd.field_name
                  AND ef.human_verified = TRUE
                ORDER BY ef.id
                LIMIT 1
            ),
            normalized_value = (
                SELECT ef.normalized_value
                FROM extracted_fields AS ef
                JOIN ocr_results AS o ON o.id = ef.ocr_result_id
                JOIN documents AS d ON d.id = o.document_id
                WHERE d.application_id = fd.application_id
                  AND ef.field_name = fd.field_name
                  AND ef.human_verified = TRUE
                ORDER BY ef.id
                LIMIT 1
            ),
            confidence_source = (
                SELECT ef.confidence_source
                FROM extracted_fields AS ef
                JOIN ocr_results AS o ON o.id = ef.ocr_result_id
                JOIN documents AS d ON d.id = o.document_id
                WHERE d.application_id = fd.application_id
                  AND ef.field_name = fd.field_name
                  AND ef.human_verified = TRUE
                ORDER BY ef.id
                LIMIT 1
            )
        WHERE fd.document_id IS NULL
        """
    )

    # -- Backfill the correction reason from the matching final review -------
    op.execute(
        """
        UPDATE feedback_dataset AS fd
        SET correction_reason = (
            SELECT hc.reason
            FROM human_corrections AS hc
            JOIN human_reviews AS hr ON hr.id = hc.review_id
            WHERE hr.application_id = fd.application_id
              AND hc.field_name = fd.field_name
            ORDER BY hc.id
            LIMIT 1
        )
        WHERE fd.correction_reason IS NULL
        """
    )

    # -- Rows belonging to an application with a final review are final -------
    op.execute(
        """
        UPDATE feedback_dataset AS fd
        SET
            decision = hr.decision::text,
            reviewer = hr.reviewer_name,
            origin = 'FINAL_HUMAN_REVIEW'
        FROM human_reviews AS hr
        WHERE hr.application_id = fd.application_id
          AND fd.origin IS NULL
        """
    )

    # -- Every remaining row was recorded by the low-confidence review --------
    op.execute(
        """
        UPDATE feedback_dataset
        SET decision = 'CORRECTED', origin = 'LOW_CONFIDENCE_REVIEW'
        WHERE origin IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_feedback_dataset_recorded_at"), table_name="feedback_dataset")
    op.drop_index(op.f("ix_feedback_dataset_origin"), table_name="feedback_dataset")
    op.drop_index(op.f("ix_feedback_dataset_decision"), table_name="feedback_dataset")
    op.drop_index(op.f("ix_feedback_dataset_reviewer"), table_name="feedback_dataset")
    op.drop_index(op.f("ix_feedback_dataset_field_name"), table_name="feedback_dataset")
    op.drop_index(op.f("ix_feedback_dataset_document_id"), table_name="feedback_dataset")
    op.drop_column("feedback_dataset", "origin")
    op.drop_column("feedback_dataset", "decision")
    op.drop_column("feedback_dataset", "reviewer")
    op.drop_column("feedback_dataset", "correction_reason")
    op.drop_column("feedback_dataset", "confidence_source")
    op.drop_column("feedback_dataset", "normalized_value")
    op.drop_column("feedback_dataset", "ocr_result_id")
    op.drop_column("feedback_dataset", "document_id")
