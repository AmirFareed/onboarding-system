"""Custom exceptions raised by the data normalization module.

Each exception carries an HTTP status code and a human-readable detail message,
mirroring the other modules' convention so the route layer can translate any
failure into a consistent, documented error response.
"""


class NormalizationError(Exception):
    """Base class for every data normalization module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Normalization failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(NormalizationError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class NoExtractedFields(NormalizationError):
    """The application has no extracted fields to normalize.

    Raised when normalization is requested before the document analysis
    pipeline produced at least one extracted field.
    """

    status_code = 422
    detail = "No extracted fields found; run document analysis first"
