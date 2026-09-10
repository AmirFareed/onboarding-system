"""Domain exceptions for the final human verification module.

Every exception carries an HTTP status code and a human-readable detail; the
module's routes translate them into ``HTTPException`` responses via the shared
``_handle_human_review_errors`` decorator.
"""


class HumanReviewError(Exception):
    """Base class for every human verification module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Human review failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(HumanReviewError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class ReviewAlreadyCompleted(HumanReviewError):
    """The application has already received a final review.

    Without an explicit reopen workflow an application can only be reviewed
    once; the system never overrides an employee's decision.
    """

    status_code = 409
    detail = "Application has already been reviewed"


class InvalidDecision(HumanReviewError):
    """The review payload is internally inconsistent."""

    status_code = 400
    detail = "Invalid review decision"


class ChecklistIncomplete(HumanReviewError):
    """An approval requires every manual checklist item to be completed."""

    status_code = 422
    detail = "The manual checklist must be completed before approving"


class MissingRejectionReason(HumanReviewError):
    """A rejection requires a mandatory rejection reason."""

    status_code = 422
    detail = "Rejection reason is required for a reject decision"


class InvalidCorrection(HumanReviewError):
    """A correction requires at least one corrected value."""

    status_code = 422
    detail = "At least one correction is required for a correct decision"


class ReviewPersistenceError(HumanReviewError):
    """The review could not be persisted."""

    status_code = 500
    detail = "Review could not be persisted"
