"""Tests for the blank issue/expiry date presence rules.

Uses the real :class:`RuleContext`/:class:`FieldValue` shapes (matching the
pattern in ``test_rule_engine_rules.py``) rather than hand-rolled doubles --
``RuleContext`` is a frozen dataclass with a fixed field set, so a partial
double drifts out of sync with it silently.
"""

from app.database.models.enums import DocumentType, ValidationStatus
from app.rule_engine.rules.date_rules import DateExpiryPresenceRule, DateIssuePresenceRule
from app.rule_engine.schemas import FieldValue, RuleContext

AMC = DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE.value


def field(field_name: str, normalized: str | None, *, doc_id: int = 1) -> FieldValue:
    """Build a field value record for a context."""
    return FieldValue(
        field_name=field_name,
        document_id=doc_id,
        document_type=AMC,
        extracted_value=normalized or "",
        normalized_value=normalized,
        verification_status="AUTO_VERIFIED",
        confidence_score=1.0,
    )


def context(fields: list[FieldValue]) -> RuleContext:
    """Build a rule context for hand-written scenarios."""
    return RuleContext(application_id=1, documents_by_type={}, fields=fields, detections={})


def test_issue_presence_rule_fails_when_blank():
    ctx = context([field("issue_date", ""), field("expiry_date", "2025-01-01")])
    result = DateIssuePresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.FAIL
    assert "missing or blank" in result.message


def test_issue_presence_rule_passes_when_present():
    ctx = context([field("issue_date", "2024-01-01"), field("expiry_date", "2025-01-01")])
    result = DateIssuePresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.PASS


def test_expiry_presence_rule_fails_when_blank():
    ctx = context([field("issue_date", "2024-01-01"), field("expiry_date", "")])
    result = DateExpiryPresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.FAIL
    assert "missing or blank" in result.message


def test_expiry_presence_rule_passes_when_present():
    ctx = context([field("issue_date", "2024-01-01"), field("expiry_date", "2025-01-01")])
    result = DateExpiryPresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.PASS


def test_issue_presence_rule_nothing_to_validate_when_absent():
    ctx = context([field("expiry_date", "2025-01-01")])
    result = DateIssuePresenceRule().evaluate(ctx)
    assert result.status == ValidationStatus.WARNING
