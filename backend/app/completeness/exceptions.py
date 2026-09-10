"""Custom exceptions raised by the completeness module.

Each exception carries an HTTP status code and a human-readable detail message,
mirroring the upload module's convention so the route layer can translate any
failure into a consistent, documented error response.
"""


class CompletenessError(Exception):
    """Base class for every completeness module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Completeness verification failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(CompletenessError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class InvalidDocumentConfiguration(CompletenessError):
    """The required/optional document configuration is inconsistent.

    Raised when the configuration in :mod:`app.completeness.constants` contains
    document types that are not part of the ``DocumentType`` enum, overlaps the
    required and optional sets, or leaves no required documents at all.
    """

    status_code = 500
    detail = "Document configuration is invalid"
