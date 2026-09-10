"""Base class and shared helpers for the business rules.

A rule is a stateless, deterministic function of a :class:`RuleContext` that
returns a :class:`RuleResult`. Rules never touch the database or raise for
business outcomes -- every branch is expressed as a status -- so the whole
ruleset can be unit-tested without any persistence layer.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.database.models.enums import ValidationStatus
from app.rule_engine.schemas import FieldValue, RuleContext, RuleResult


class BaseRule(ABC):
    """Contract every business rule implements.

    Attributes:
        id: Stable, unique identifier of the rule (persisted per run).
        name: Human-readable rule name.
        category: Category identifier the rule belongs to (a key of
            ``RULE_CATEGORIES``).
    """

    id: ClassVar[str]
    name: ClassVar[str]
    category: ClassVar[str]

    @abstractmethod
    def evaluate(self, context: RuleContext) -> RuleResult:
        """Evaluate the rule against ``context`` and return its outcome.

        Implementations return a result via :meth:`result`, never raise for a
        business outcome, and mark the documents/fields they related to so the
        persisted row carries the context of the decision.
        """

    # -- Result construction --------------------------------------------------

    def result(
        self,
        status: ValidationStatus,
        message: str,
        *,
        related_document_ids: list[int] | None = None,
        related_field_names: list[str] | None = None,
    ) -> RuleResult:
        """Build a result for this rule's identity.

        Args:
            status: Resolution state of the rule.
            message: Human-readable explanation of the outcome.
            related_document_ids: Documents the rule related to.
            related_field_names: Field names the rule related to.

        Returns:
            A fully populated rule result.
        """
        return RuleResult(
            rule_id=self.id,
            rule_name=self.name,
            category=self.category,
            status=status,
            message=message,
            related_document_ids=related_document_ids or [],
            related_field_names=related_field_names or [],
        )


# -- Shared field/document selection helpers ----------------------------------


def field_values(
    context: RuleContext,
    field_name: str,
    document_types: set[str] | None = None,
) -> list[FieldValue]:
    """Return the field rows for ``field_name``, optionally by document type.

    Args:
        context: Application context to inspect.
        field_name: Machine-readable name of the field.
        document_types: When given, only fields from documents of these types
            are returned.

    Returns:
        The matching field rows in stable application order.
    """
    values = context.values(field_name)
    if document_types is None:
        return values
    return [
        value for value in values if value.document_type in document_types
    ]


def normalized_values(
    context: RuleContext,
    field_name: str,
    document_types: set[str] | None = None,
) -> list[str]:
    """Return the non-empty normalized values of a field, deduplicated.

    Args:
        context: Application context to inspect.
        field_name: Machine-readable name of the field.
        document_types: When given, only fields from documents of these types
            are considered.

    Returns:
        The canonical values in stable application order.
    """
    values: list[str] = []
    for value in field_values(context, field_name, document_types):
        normalized = (value.normalized_value or "").strip()
        if normalized and normalized not in values:
            values.append(normalized)
    return values
