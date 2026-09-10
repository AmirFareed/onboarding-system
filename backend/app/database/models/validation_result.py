"""Validation result model.

Records the outcome of a single validation check. The rule engine (business
rules) stores one row per executed rule; the technical validation module stores
one row per technical check. Both use the same table, distinguished by
``rule_category``. The technical validation columns (``document_id``,
``blur_score``, ``rotation_angle``, ``file_format``) are ``NULL`` for rows
written by the rule engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import Severity, ValidationStatus

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.document import Document


class ValidationResult(Base):
    """Outcome of a single validation check for an application.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Application being validated (foreign key, cascades).
        document_id: Document the check belongs to, or ``None`` for checks that
            are not document-scoped (e.g. rule-engine results).
        rule_id: Opaque identifier of the executed check.
        rule_name: Human-readable check name.
        rule_category: Grouping of the check (e.g. signature, stamp,
            technical_validation).
        severity: Importance level of the check.
        status: Resolution state of the check.
        message: Human-readable explanation of the outcome.
        related_document_ids: Documents the check relates to (rule-engine rows).
        related_field_names: Field names the check relates to (rule-engine rows).
        blur_score: Variance-of-Laplacian sharpness score (technical checks).
        rotation_angle: Estimated rotation in degrees (technical checks).
        file_format: Normalized detected file format (technical checks).
        validated_at: When the check was executed (UTC).
    """

    __tablename__ = "validation_results"
    __table_args__ = (
        Index("ix_validation_results_application_id", "application_id"),
        Index("ix_validation_results_document_id", "document_id"),
        Index("ix_validation_results_rule_id", "rule_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[Severity] = mapped_column(nullable=False)
    status: Mapped[ValidationStatus] = mapped_column(
        default=ValidationStatus.PENDING_MANUAL_REVIEW,
        server_default=text("'PENDING_MANUAL_REVIEW'"),
        nullable=False,
    )
    message: Mapped[str | None] = mapped_column(Text)
    related_document_ids: Mapped[list[int] | None] = mapped_column(JSON)
    related_field_names: Mapped[list[str] | None] = mapped_column(JSON)
    blur_score: Mapped[float | None] = mapped_column(Float)
    rotation_angle: Mapped[float | None] = mapped_column(Float)
    file_format: Mapped[str | None] = mapped_column(String(10))
    validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    application: Mapped[Application] = relationship(back_populates="validation_results")
    document: Mapped[Document | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ValidationResult id={self.id} rule={self.rule_id} status={self.status}>"
