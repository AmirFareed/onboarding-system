"""Domain exceptions for the feedback module.

Every exception carries an HTTP status code and a human-readable detail; the
module's routes translate them into ``HTTPException`` responses via the shared
``_handle_feedback_errors`` decorator.
"""


class FeedbackError(Exception):
    """Base class for every feedback module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Feedback module failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class FeedbackNotFound(FeedbackError):
    """The requested feedback entry does not exist."""

    status_code = 404
    detail = "Feedback entry not found"


class InvalidFilter(FeedbackError):
    """The feedback filter combination is semantically invalid."""

    status_code = 422
    detail = "Invalid feedback filter"


class ExportFailed(FeedbackError):
    """The feedback dataset could not be exported."""

    status_code = 500
    detail = "Feedback dataset export failed"
