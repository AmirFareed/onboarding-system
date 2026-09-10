"""Pure validation helpers for the final human verification module.

Everything here is a deterministic function of the review payload, so the
decision rules can be unit-tested without a database. The service hands the
validated request to these helpers; no persistence or pipeline logic ever lives
here.
"""

from __future__ import annotations

from app.database.models.enums import ApplicationStatus, ReviewDecision
from app.human_verification.constants import CHECKLIST_ITEMS, DECISION_TO_STATUS
from app.human_verification.exceptions import (
    ChecklistIncomplete,
    InvalidCorrection,
    InvalidDecision,
    MissingRejectionReason,
)
from app.human_verification.schemas import ChecklistItem, HumanReviewRequest


def decision_to_status(decision: ReviewDecision) -> ApplicationStatus:
    """Return the application status reached by a review decision.

    Args:
        decision: The employee's decision.

    Returns:
        The application status the decision maps to.
    """
    return DECISION_TO_STATUS[decision]


def validate_decision_rules(request: HumanReviewRequest) -> None:
    """Enforce the decision-specific validation rules on a review payload.

    Every decision is internally consistent: an approval requires the complete
    checklist and carries no corrections or rejection reason, a correction
    requires at least one corrected value, and a rejection requires a mandatory
    rejection reason. Checklist item names must belong to the fixed checklist
    vocabulary and be listed at most once.

    Args:
        request: Review payload to validate.

    Raises:
        InvalidDecision: When the payload is internally inconsistent or
            references unknown checklist items.
        ChecklistIncomplete: When an approval is missing checked checklist
            items.
        InvalidCorrection: When a correction decision carries no corrections.
        MissingRejectionReason: When a rejection carries no rejection reason.
    """
    _validate_checklist_names(request)
    if request.decision is ReviewDecision.APPROVE:
        _validate_approve(request)
    elif request.decision is ReviewDecision.CORRECT:
        _validate_correct(request)
    else:
        _validate_reject(request)


def _validate_checklist_names(request: HumanReviewRequest) -> None:
    """Reject unknown or duplicated checklist item names."""
    known = set(CHECKLIST_ITEMS)
    seen: set[str] = set()
    for item in request.checklist:
        if item.item_name not in known:
            raise InvalidDecision(
                f"Unknown checklist item: {item.item_name!r}"
            )
        if item.item_name in seen:
            raise InvalidDecision(
                f"Checklist item listed more than once: {item.item_name!r}"
            )
        seen.add(item.item_name)


def _validate_approve(request: HumanReviewRequest) -> None:
    """An approval requires the full checklist and carries no corrections."""
    if request.rejection_reason and request.rejection_reason.strip():
        raise InvalidDecision("An approval cannot carry a rejection reason")
    if request.corrections:
        raise InvalidDecision("An approval cannot carry corrections")
    checked = {item.item_name for item in request.checklist if item.is_checked}
    missing = [name for name in CHECKLIST_ITEMS if name not in checked]
    if missing:
        raise ChecklistIncomplete(
            f"Checklist items not completed: {', '.join(missing)}"
        )


def _validate_correct(request: HumanReviewRequest) -> None:
    """A correction requires at least one corrected value."""
    if request.rejection_reason and request.rejection_reason.strip():
        raise InvalidDecision("A correction cannot carry a rejection reason")
    if not request.corrections:
        raise InvalidCorrection()
    # A correction is unique per (document, field name) when document_id is
    # given, so two documents extracting the same field name can each be
    # corrected once. Without document_id, uniqueness falls back to field
    # name alone, same as before document_id existed.
    keys = [(item.document_id, item.field_name) for item in request.corrections]
    if len(keys) != len(set(keys)):
        raise InvalidDecision("A field can only be corrected once per review")


def _validate_reject(request: HumanReviewRequest) -> None:
    """A rejection requires a mandatory rejection reason and no corrections."""
    if request.corrections:
        raise InvalidDecision("A rejection cannot carry corrections")
    if not request.rejection_reason or not request.rejection_reason.strip():
        raise MissingRejectionReason()


def checklist_state(checklist: list[ChecklistItem]) -> dict[str, bool]:
    """Collapse a submitted checklist into an item-name-to-checked mapping.

    Args:
        checklist: Checklist items submitted with the review.

    Returns:
        A mapping of item name to checked state.
    """
    return {item.item_name: item.is_checked for item in checklist}


__all__ = [
    "checklist_state",
    "decision_to_status",
    "validate_decision_rules",
]
