"""Tests for the final human verification decision rules.

The decision rules are pure functions of the review payload, so they are tested
here without a database: the decision-to-status mapping, the mandatory checklist
completeness for approvals, the mandatory rejection reason and the correction
requirements.
"""

import pytest

from app.database.models.enums import ApplicationStatus, ReviewDecision
from app.human_verification.constants import CHECKLIST_ITEMS
from app.human_verification.exceptions import (
    ChecklistIncomplete,
    InvalidCorrection,
    InvalidDecision,
    MissingRejectionReason,
)
from app.human_verification.schemas import ChecklistItem, CorrectionItem, HumanReviewRequest
from app.human_verification.validators import decision_to_status, validate_decision_rules


def request(
    *,
    decision: ReviewDecision,
    comments: str | None = None,
    rejection_reason: str | None = None,
    checklist: list[ChecklistItem] | None = None,
    corrections: list[CorrectionItem] | None = None,
) -> HumanReviewRequest:
    """Build a review request with the provided payload."""
    return HumanReviewRequest(
        decision=decision,
        comments=comments,
        rejection_reason=rejection_reason,
        checklist=checklist or [],
        corrections=corrections or [],
    )


def checked_items(count: int | None = None) -> list[ChecklistItem]:
    """Return the given number of fully checked checklist items."""
    names = list(CHECKLIST_ITEMS) if count is None else list(CHECKLIST_ITEMS)[:count]
    return [ChecklistItem(item_name=name, is_checked=True) for name in names]


def correction(field: str = "account_number", value: str = "9999999999") -> CorrectionItem:
    """Return a single correction item."""
    return CorrectionItem(field_name=field, corrected_value=value, reason="manual fix")


# --- Decision to status ------------------------------------------------------


def test_decision_to_status_maps_every_decision():
    assert decision_to_status(ReviewDecision.APPROVE) is ApplicationStatus.APPROVED
    assert decision_to_status(ReviewDecision.CORRECT) is ApplicationStatus.CORRECTED
    assert decision_to_status(ReviewDecision.REJECT) is ApplicationStatus.REJECTED


# --- Approve rules -----------------------------------------------------------


def test_approve_with_full_checklist_is_valid():
    validate_decision_rules(request(decision=ReviewDecision.APPROVE, checklist=checked_items()))


def test_approve_missing_item_raises():
    with pytest.raises(ChecklistIncomplete):
        validate_decision_rules(
            request(
                decision=ReviewDecision.APPROVE,
                checklist=checked_items(len(CHECKLIST_ITEMS) - 1),
            )
        )


def test_approve_unchecked_item_raises():
    items = checked_items()
    items[0].is_checked = False
    with pytest.raises(ChecklistIncomplete):
        validate_decision_rules(request(decision=ReviewDecision.APPROVE, checklist=items))


def test_approve_with_corrections_is_inconsistent():
    with pytest.raises(InvalidDecision):
        validate_decision_rules(
            request(
                decision=ReviewDecision.APPROVE,
                checklist=checked_items(),
                corrections=[correction()],
            )
        )


def test_approve_with_rejection_reason_is_inconsistent():
    with pytest.raises(InvalidDecision):
        validate_decision_rules(
            request(
                decision=ReviewDecision.APPROVE,
                checklist=checked_items(),
                rejection_reason="tampered",
            )
        )


# --- Correction rules --------------------------------------------------------


def test_correct_with_correction_is_valid():
    validate_decision_rules(
        request(decision=ReviewDecision.CORRECT, corrections=[correction()])
    )


def test_correct_without_corrections_raises():
    with pytest.raises(InvalidCorrection):
        validate_decision_rules(request(decision=ReviewDecision.CORRECT))


def test_correct_with_duplicate_field_raises():
    with pytest.raises(InvalidDecision):
        validate_decision_rules(
            request(
                decision=ReviewDecision.CORRECT,
                corrections=[
                    correction(),
                    correction(field="account_number", value="7777777777"),
                ],
            )
        )


def test_correct_with_rejection_reason_is_inconsistent():
    with pytest.raises(InvalidDecision):
        validate_decision_rules(
            request(
                decision=ReviewDecision.CORRECT,
                corrections=[correction()],
                rejection_reason="nope",
            )
        )


# --- Reject rules ------------------------------------------------------------


def test_reject_with_reason_is_valid():
    validate_decision_rules(
        request(decision=ReviewDecision.REJECT, rejection_reason="tampered document")
    )


def test_reject_without_reason_raises():
    with pytest.raises(MissingRejectionReason):
        validate_decision_rules(request(decision=ReviewDecision.REJECT))


def test_reject_with_blank_reason_raises():
    with pytest.raises(MissingRejectionReason):
        validate_decision_rules(
            request(decision=ReviewDecision.REJECT, rejection_reason="   ")
        )


def test_reject_with_corrections_is_inconsistent():
    with pytest.raises(InvalidDecision):
        validate_decision_rules(
            request(
                decision=ReviewDecision.REJECT,
                rejection_reason="tampered",
                corrections=[correction()],
            )
        )


# --- Checklist vocabulary ----------------------------------------------------


def test_unknown_checklist_item_raises():
    with pytest.raises(InvalidDecision):
        validate_decision_rules(
            request(
                decision=ReviewDecision.APPROVE,
                checklist=checked_items() + [ChecklistItem(item_name="Unknown item")],
            )
        )


def test_duplicate_checklist_item_raises():
    items = checked_items()
    items.append(ChecklistItem(item_name=CHECKLIST_ITEMS[0], is_checked=True))
    with pytest.raises(InvalidDecision):
        validate_decision_rules(request(decision=ReviewDecision.APPROVE, checklist=items))
