"""Regression tests for audit-log atomicity in confidence and normalization.

The business-data mutation and its audit-log write must be one transaction:
a failed audit write must roll the mutation back, and a successful run must
persist both. Reproduces the reported bug (docs/TEAMMATE_BUG_TRIAGE.md #6): in
both ``confidence/services.py::review`` and ``normalization/services.py::normalize``
the business mutation was committed (``self._db.commit()``) *before* the audit
log was written, so a failed audit write left the state change durable with no
audit trail.

These tests drive the service layer directly with a real session so the exact
transaction boundary (commit/rollback) is observable; the surrounding API path
is already covered by the existing confidence/normalization test files.
"""

import pytest
from sqlalchemy.orm import Session

from app.confidence.constants import ACTION_EVALUATED, ACTION_REVIEWED
from app.confidence.schemas import ReviewDecisionInput, ReviewDecisionType, ReviewRequest
from app.confidence.services import ConfidenceService
from app.database.connection import SessionLocal
from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.extracted_field_repository import ExtractedFieldRepository
from app.normalization.constants import ACTION_NORMALIZED
from app.normalization.services import NormalizationService
from tests.test_confidence_api import (
    add_digital_statement,
    add_scanned_statement,
    audit_actions,
    evaluate as api_evaluate,
    stored_fields,
)

API = "/api/v1"
REVIEW_URL = "/confidence/review"


def _new_session() -> Session:
    """A fresh session bound to the dedicated test database."""
    return SessionLocal()


def _failing_audit_factory(actions_to_fail):
    """Return a monkeypatchable ``AuditLogRepository.create`` that raises for
    the given actions and delegates everything else to the real implementation.

    Failing a *specific* action reproduces the reported failure mode precisely:
    the business mutation (and any per-field audits) commits first, then the
    summary audit write fails -- exactly what the buggy call sites allowed.
    """

    original = AuditLogRepository.create

    def failing_audit(self, **kwargs):
        if kwargs.get("action") in actions_to_fail:
            raise RuntimeError("simulated audit write failure")
        return original(self, **kwargs)

    return failing_audit


# --- Normalization -----------------------------------------------------------


def test_normalize_success_persists_mutation_and_audit(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)
    api_evaluate(authenticated_client, application_id)

    db = _new_session()
    try:
        result = NormalizationService(db).normalize(application_id=application_id)
    finally:
        db.close()

    assert result.processing_status == "READY_FOR_BUSINESS_VALIDATION"
    fields = stored_fields(application_id)
    assert fields["iban"].normalized_value == "DE89370400440532013000"
    assert ACTION_NORMALIZED in audit_actions(application_id)


def test_normalize_failure_persists_neither(authenticated_client, storage_root, monkeypatch):
    application_id = add_digital_statement(authenticated_client, storage_root)
    api_evaluate(authenticated_client, application_id)
    # evaluate() already seeds normalized_value with the extracted value; the
    # canonical (compact) form is what a successful normalize would overwrite it
    # with. Capture the pre-normalize value and assert it is untouched after the
    # failed run -- the buggy code left the canonical form persisted instead.
    before = stored_fields(application_id)["iban"].normalized_value

    monkeypatch.setattr(
        AuditLogRepository,
        "create",
        _failing_audit_factory({ACTION_NORMALIZED}),
    )
    db = _new_session()
    with pytest.raises(RuntimeError, match="simulated audit write failure"):
        NormalizationService(db).normalize(application_id=application_id)
    db.close()

    # Failure must roll the mutation back too: no canonical value, no audit row.
    assert stored_fields(application_id)["iban"].normalized_value == before
    assert ACTION_NORMALIZED not in audit_actions(application_id)


# --- Confidence review -------------------------------------------------------


def test_review_success_persists_mutation_and_audits(
    authenticated_client, storage_root, monkeypatch
):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = api_evaluate(authenticated_client, application_id)["fields_requiring_review"]

    request = ReviewRequest(
        decisions=[
            ReviewDecisionInput(
                field_name=field["field_name"],
                decision=ReviewDecisionType.VERIFIED,
            )
            for field in flagged
        ]
    )
    db = _new_session()
    try:
        result = ConfidenceService(db).review(
            application_id=application_id,
            request=request,
            reviewer_name="Test Operator",
        )
    finally:
        db.close()

    assert result.processing_status.value == "READY_FOR_NORMALIZATION"
    fields = stored_fields(application_id)
    assert all(f.human_verified for f in fields.values())
    actions = audit_actions(application_id)
    assert ACTION_REVIEWED in actions
    assert actions.count("confidence.field_verified") == len(flagged)


def test_review_failure_rolls_back_mutation_and_audits(
    authenticated_client, storage_root, monkeypatch
):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = api_evaluate(authenticated_client, application_id)["fields_requiring_review"]
    # Fail only the summary audit: the per-field decisions run first, so in the
    # buggy code the field mutations were already committed before the summary
    # audit write failed.
    monkeypatch.setattr(
        AuditLogRepository,
        "create",
        _failing_audit_factory({ACTION_REVIEWED}),
    )

    request = ReviewRequest(
        decisions=[
            ReviewDecisionInput(
                field_name=field["field_name"],
                decision=ReviewDecisionType.VERIFIED,
            )
            for field in flagged
        ]
    )
    db = _new_session()
    with pytest.raises(RuntimeError, match="simulated audit write failure"):
        ConfidenceService(db).review(
            application_id=application_id,
            request=request,
            reviewer_name="Test Operator",
        )
    # The service rolled back the same session. SQLAlchemy expired every object
    # in its identity map, so re-querying through this very session reloads the
    # field rows from the rolled-back database: the in-memory mutations are
    # gone too, not just the committed rows.
    reloaded = ExtractedFieldRepository(db).get_by_application(application_id)
    assert all(not f.human_verified for f in reloaded)
    db.close()

    # Neither the field mutations nor any audit row may survive the rollback.
    assert all(not f.human_verified for f in stored_fields(application_id).values())
    assert ACTION_REVIEWED not in audit_actions(application_id)
    assert "confidence.field_verified" not in audit_actions(application_id)


def test_review_corrected_failure_rolls_back_feedback_and_audit(
    authenticated_client, storage_root, monkeypatch
):
    """A CORRECTED decision must not leak a feedback sample or an audit row
    when the summary audit fails: the reordered audit-before-feedback writes
    (both commit=False) mean the whole review shares one transaction."""
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = api_evaluate(authenticated_client, application_id)["fields_requiring_review"]
    monkeypatch.setattr(
        AuditLogRepository,
        "create",
        _failing_audit_factory({ACTION_REVIEWED}),
    )

    request = ReviewRequest(
        decisions=[
            ReviewDecisionInput(
                field_name="account_number",
                decision=ReviewDecisionType.CORRECTED,
                corrected_value="9999999999",
            ),
            *[
                ReviewDecisionInput(
                    field_name=field["field_name"],
                    decision=ReviewDecisionType.VERIFIED,
                )
                for field in flagged
                if field["field_name"] != "account_number"
            ],
        ]
    )
    db = _new_session()
    with pytest.raises(RuntimeError, match="simulated audit write failure"):
        ConfidenceService(db).review(
            application_id=application_id,
            request=request,
            reviewer_name="Test Operator",
        )
    db.close()

    fields = stored_fields(application_id)
    assert all(not f.human_verified for f in fields.values())
    assert fields["account_number"].human_corrected_value is None
    assert fields["account_number"].extracted_value == "1234567890"
    # Only the earlier successful evaluate() audit remains; no review action
    # (per-field or summary) may survive the rollback.
    actions = audit_actions(application_id)
    assert actions == ["confidence.evaluated"]


# --- Confidence evaluation ---------------------------------------------------


def test_evaluate_success_persists_fields_and_audit(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)

    db = _new_session()
    try:
        result = ConfidenceService(db).evaluate(application_id=application_id)
    finally:
        db.close()

    assert result.processing_status.value == "READY_FOR_NORMALIZATION"
    assert len(stored_fields(application_id)) == 11
    assert ACTION_EVALUATED in audit_actions(application_id)


def test_evaluate_failure_rolls_back_fields_and_audit(authenticated_client, storage_root, monkeypatch):
    application_id = add_digital_statement(authenticated_client, storage_root)

    monkeypatch.setattr(
        AuditLogRepository,
        "create",
        _failing_audit_factory({ACTION_EVALUATED}),
    )
    db = _new_session()
    with pytest.raises(RuntimeError, match="simulated audit write failure"):
        ConfidenceService(db).evaluate(application_id=application_id)
    db.close()

    # No field rows and no audit row may survive the rollback.
    assert stored_fields(application_id) == {}
    assert ACTION_EVALUATED not in audit_actions(application_id)