"""Custom exceptions raised by the operator workflow module."""


class OperatorWorkflowError(Exception):
    """Base class for every operator workflow error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Operator workflow operation failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(OperatorWorkflowError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class InvalidTransition(OperatorWorkflowError):
    """The application is not in a state that permits the requested action."""

    status_code = 409
    detail = "The application is not in a state that permits this action"


class ApplicationComplete(OperatorWorkflowError):
    """Requested documents for an application that has nothing missing."""

    status_code = 422
    detail = "No documents are missing for this application"


class IncompleteApplication(OperatorWorkflowError):
    """An operator submitted an application whose document set is incomplete."""

    status_code = 422
    detail = "Cannot submit an application with missing required documents"


class MissingReason(OperatorWorkflowError):
    """An operator rejected an application without a reason."""

    status_code = 422
    detail = "A rejection reason is required"