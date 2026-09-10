"""Final human verification module.

This is the last decision stage of the verification pipeline: the employee
reviews the validation report together with the uploaded documents and records
the final business decision (approve, correct or reject). The module performs no
OCR, no normalization, no rule validation and no report generation; it only
reads the stored pipeline outputs and records the review, checklist, corrections
and audit trail. The system never overrides the employee's decision.
"""

from app.human_verification.constants import (
    ACTION_APPLICATION_APPROVED,
    ACTION_APPLICATION_CORRECTED,
    ACTION_APPLICATION_REJECTED,
    ACTION_CHECKLIST_COMPLETED,
    ACTION_REVIEW_OPENED,
    ACTION_REVIEW_SUBMITTED,
    CHECKLIST_ITEMS,
    DECISION_TO_STATUS,
    DECISIONS,
    REVIEW_VERSION,
)
from app.human_verification.exceptions import (
    ApplicationNotFound,
    ChecklistIncomplete,
    HumanReviewError,
    InvalidCorrection,
    InvalidDecision,
    MissingRejectionReason,
    ReviewAlreadyCompleted,
    ReviewPersistenceError,
)
from app.human_verification.routes import router
from app.human_verification.services import HumanVerificationService

__all__ = [
    "ACTION_APPLICATION_APPROVED",
    "ACTION_APPLICATION_CORRECTED",
    "ACTION_APPLICATION_REJECTED",
    "ACTION_CHECKLIST_COMPLETED",
    "ACTION_REVIEW_OPENED",
    "ACTION_REVIEW_SUBMITTED",
    "CHECKLIST_ITEMS",
    "DECISIONS",
    "DECISION_TO_STATUS",
    "REVIEW_VERSION",
    "ApplicationNotFound",
    "ChecklistIncomplete",
    "HumanReviewError",
    "HumanVerificationService",
    "InvalidCorrection",
    "InvalidDecision",
    "MissingRejectionReason",
    "ReviewAlreadyCompleted",
    "ReviewPersistenceError",
    "router",
]
