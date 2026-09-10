"""Repository for the ValidationResult entity."""

from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database.models.enums import Severity, ValidationStatus
from app.database.models.validation_result import ValidationResult
from app.database.repositories.base import BaseRepository


class ValidationRepository(BaseRepository[ValidationResult]):
    """Persistence operations for :class:`ValidationResult`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[ValidationResult]:
        return ValidationResult

    def create(
        self,
        *,
        application_id: int,
        rule_id: str,
        rule_name: str,
        rule_category: str,
        severity: Severity,
        status: ValidationStatus = ValidationStatus.PENDING_MANUAL_REVIEW,
        message: str | None = None,
        document_id: int | None = None,
        related_document_ids: list[int] | None = None,
        related_field_names: list[str] | None = None,
        blur_score: float | None = None,
        rotation_angle: float | None = None,
        file_format: str | None = None,
        validated_at: datetime | None = None,
    ) -> ValidationResult:
        """Create and persist a new validation result.

        Args:
            application_id: Application being validated.
            rule_id: Opaque identifier of the executed check.
            rule_name: Human-readable check name.
            rule_category: Grouping of the check.
            severity: Importance level of the check.
            status: Resolution state of the check.
            message: Optional human-readable explanation.
            document_id: Optional document the check applies to (technical
                validation rows). ``None`` for application-level checks.
            related_document_ids: Optional documents the check relates to
                (rule-engine rows).
            related_field_names: Optional field names the check relates to
                (rule-engine rows).
            blur_score: Optional sharpness score for blur checks.
            rotation_angle: Optional estimated rotation for rotation checks.
            file_format: Optional normalized format label for file-type checks.
            validated_at: Optional explicit validation timestamp. When given it
                is stored verbatim so every check of one run shares the same
                timestamp.

        Returns:
            The persisted validation result.
        """
        validation_result = ValidationResult(
            application_id=application_id,
            document_id=document_id,
            rule_id=rule_id,
            rule_name=rule_name,
            rule_category=rule_category,
            severity=severity,
            status=status,
            message=message,
            related_document_ids=related_document_ids,
            related_field_names=related_field_names,
            blur_score=blur_score,
            rotation_angle=rotation_angle,
            file_format=file_format,
            validated_at=validated_at,
        )
        self._db.add(validation_result)
        return self._commit_and_refresh(validation_result)

    def get_by_application(
        self,
        application_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[ValidationResult]:
        """Return validation results for an application.

        Args:
            application_id: Application id to look up.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of validation results ordered by validation date.
        """
        statement = (
            select(ValidationResult)
            .where(ValidationResult.application_id == application_id)
            .order_by(ValidationResult.validated_at.desc(), ValidationResult.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return self._db.scalars(statement).all()

    def count_by_application(self, application_id: int) -> int:
        """Return the number of validation results for an application.

        Args:
            application_id: Application id to look up.

        Returns:
            The number of validation results for the application.
        """
        statement = select(func.count(ValidationResult.id)).where(
            ValidationResult.application_id == application_id
        )
        return self._db.execute(statement).scalar_one()

    def get_by_application_and_category(
        self,
        application_id: int,
        rule_category: str,
    ) -> Sequence[ValidationResult]:
        """Return validation results of one category for an application.

        Groups every check of a single validation run together: rows are
        ordered by document, then by validation timestamp descending so each
        document's latest run comes first.

        Args:
            application_id: Application id to look up.
            rule_category: Category of checks to return (e.g.
                ``technical_validation``).

        Returns:
            A sequence of validation results ordered by document and run time.
        """
        statement = (
            select(ValidationResult)
            .where(
                ValidationResult.application_id == application_id,
                ValidationResult.rule_category == rule_category,
            )
            .order_by(
                ValidationResult.document_id,
                ValidationResult.validated_at.desc(),
                ValidationResult.id.desc(),
            )
        )
        return self._db.scalars(statement).all()

    def get_by_application_and_categories(
        self,
        application_id: int,
        rule_categories: Iterable[str],
    ) -> Sequence[ValidationResult]:
        """Return validation results of several categories for an application.

        Args:
            application_id: Application id to look up.
            rule_categories: Categories of results to return.

        Returns:
            A sequence of validation results ordered by validation date.
        """
        statement = (
            select(ValidationResult)
            .where(
                ValidationResult.application_id == application_id,
                ValidationResult.rule_category.in_(list(rule_categories)),
            )
            .order_by(
                ValidationResult.validated_at.desc(),
                ValidationResult.id.desc(),
            )
        )
        return self._db.scalars(statement).all()

    def delete_by_application_and_categories(
        self,
        application_id: int,
        rule_categories: Iterable[str],
    ) -> int:
        """Delete the validation results of several categories for an application.

        Used by the rule engine to give each validation run replace semantics:
        re-running validation refreshes the stored rule rows instead of
        accumulating duplicates.

        Args:
            application_id: Application id whose results are deleted.
            rule_categories: Categories of results to delete.

        Returns:
            The number of deleted rows.
        """
        result = self._db.execute(
            delete(ValidationResult).where(
                ValidationResult.application_id == application_id,
                ValidationResult.rule_category.in_(list(rule_categories)),
            )
        )
        self._db.commit()
        return result.rowcount or 0
