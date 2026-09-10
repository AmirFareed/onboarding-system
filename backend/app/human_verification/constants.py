"""Configuration for the final human verification module.

Centralizes the module version, the mandatory manual-review checklist, the
decision-to-status mapping and the audit action identifiers. This phase only
records the employee's review and decision -- it never runs OCR, normalization,
rule validation or report generation -- so the constants here are the fixed
vocabulary the rest of the module shares.
"""

from app.database.models.enums import ApplicationStatus, ReviewDecision

#: Version of the human review logic. Bumped whenever the decision rules, the
#: checklist or the audit vocabulary changes so a stored review can be traced
#: to the exact logic that produced it.
REVIEW_VERSION: str = "1.0.0"

#: Every decision supported by the final review. The values mirror the existing
#: ``ReviewDecision`` enum consumed by the ``human_reviews`` table.
DECISIONS: tuple[ReviewDecision, ...] = (
    ReviewDecision.APPROVE,
    ReviewDecision.CORRECT,
    ReviewDecision.REJECT,
)

#: Application status reached by each decision. The system never overrides the
#: employee's decision: APPROVE approves, CORRECT marks the application
#: corrected and REJECT rejects it.
DECISION_TO_STATUS: dict[ReviewDecision, ApplicationStatus] = {
    ReviewDecision.APPROVE: ApplicationStatus.APPROVED,
    ReviewDecision.CORRECT: ApplicationStatus.CORRECTED,
    ReviewDecision.REJECT: ApplicationStatus.REJECTED,
}

#: The mandatory manual-review checklist. An APPROVE decision requires every
#: item to be checked; items are stored individually in ``manual_checklists``
#: keyed on the item name, so the checklist state survives per item with its own
#: reviewer and timestamp.
CHECKLIST_ITEMS: tuple[str, ...] = (
    "Bank Maintenance Certificate originality confirmed",
    "Authority Letter signature confirmed",
    "Account Maintenance Certificate signature confirmed",
    "1-Link Application signature confirmed",
    "Tripartite Agreement signature confirmed",
    "Business Requirement Document signature confirmed",
    "Formal Request Letter signature confirmed",
    "Schedule of Charges / Bilateral signature confirmed",
    "Account Maintenance Certificate stamp confirmed",
    "1-Link Application stamp confirmed",
    "Tripartite Agreement stamp confirmed",
    "Schedule of Charges / Bilateral stamp confirmed",
    "Critical validation errors reviewed",
    "Validation report reviewed",
)


# -- Audit actions ------------------------------------------------------------
#: Audit action recorded when the review screen is opened.
ACTION_REVIEW_OPENED: str = "human_review.opened"
#: Audit action recorded when a final decision is submitted.
ACTION_REVIEW_SUBMITTED: str = "human_review.submitted"
#: Audit action recorded when an application is approved.
ACTION_APPLICATION_APPROVED: str = "human_review.application_approved"
#: Audit action recorded when an application is corrected.
ACTION_APPLICATION_CORRECTED: str = "human_review.application_corrected"
#: Audit action recorded when an application is rejected.
ACTION_APPLICATION_REJECTED: str = "human_review.application_rejected"
#: Audit action recorded when the full manual checklist is completed.
ACTION_CHECKLIST_COMPLETED: str = "human_review.checklist_completed"


# -- OCR outcome vocabulary ---------------------------------------------------
#: Document has no stored OCR result.
OCR_STATUS_NOT_PROCESSED: str = "NOT_PROCESSED"
#: Document text was produced by OCR over rendered pages.
OCR_STATUS_OCR_PROCESSED: str = "OCR_PROCESSED"
#: Document text was extracted natively from a digital PDF.
OCR_STATUS_TEXT_EXTRACTED: str = "TEXT_EXTRACTED"

#: Length of the raw OCR text preview included in the review screen.
OCR_PREVIEW_LENGTH: int = 1000


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
    "OCR_PREVIEW_LENGTH",
    "OCR_STATUS_NOT_PROCESSED",
    "OCR_STATUS_OCR_PROCESSED",
    "OCR_STATUS_TEXT_EXTRACTED",
    "REVIEW_VERSION",
]
