"""Custom exceptions raised by the business rule engine module.

Each exception carries an HTTP status code and a human-readable detail message,
mirroring the other modules' convention so the route layer can translate any
failure into a consistent, documented error response. Rule execution itself
never raises here: individual rule failures are captured per rule and logged.
"""


class RuleEngineError(Exception):
    """Base class for every business rule engine module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Business rule validation failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(RuleEngineError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"
