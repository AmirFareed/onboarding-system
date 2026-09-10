"""Custom exceptions raised by the confidence scoring module.

Each exception carries an HTTP status code and a human-readable detail message,
mirroring the other modules' convention so the route layer can translate any
failure into a consistent, documented error response.
"""


class ConfidenceError(Exception):
    """Base class for every confidence scoring module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Confidence scoring failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(ConfidenceError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class NoAnalysisResults(ConfidenceError):
    """The application has no analyzed documents to score.

    Raised when confidence evaluation is requested before the document analysis
    pipeline produced at least one result.
    """

    status_code = 422
    detail = "No analysis results found; run document analysis first"


class ReviewNotRequired(ConfidenceError):
    """No human review is outstanding for the application.

    Raised when a review is submitted for an application that was never
    evaluated or whose evaluation finished with no fields pending review.
    """

    status_code = 422
    detail = "No confidence evaluation requires human review"


class InvalidReviewPayload(ConfidenceError):
    """The review payload does not match the fields flagged for review."""

    status_code = 422
    detail = "Invalid review payload"


class ReviewAlreadyApplied(ConfidenceError):
    """Every flagged field has already been reviewed."""

    status_code = 409
    detail = "Confidence review has already been applied"


class EvaluationFailed(ConfidenceError):
    """The confidence evaluation failed to complete."""

    status_code = 500
    detail = "Confidence evaluation failed"
