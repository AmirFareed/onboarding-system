"""Custom exceptions raised by the technical validation module.

Each exception carries an HTTP status code so the route layer can translate any
failure that escapes the module into a consistent, documented error response.
Document-scoped failures (missing file, corrupted PDF, ...) are normally caught
by the service and recorded inside the per-document report; they only reach the
HTTP layer when a request-level condition (application missing) or a
catastrophic failure occurs.
"""


class TechnicalValidationError(Exception):
    """Base class for every technical validation module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Technical validation failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(TechnicalValidationError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class FileNotFound(TechnicalValidationError):
    """The stored file for a document is missing from the storage backend."""

    status_code = 422
    detail = "Stored file not found"


class FileUnreadable(TechnicalValidationError):
    """The stored file exists but cannot be read."""

    status_code = 422
    detail = "Stored file is not readable"


class EmptyFile(TechnicalValidationError):
    """The stored file contains no data."""

    status_code = 422
    detail = "Stored file is empty"


class CorruptedPDF(TechnicalValidationError):
    """The PDF cannot be opened, is damaged or contains no pages."""

    status_code = 422
    detail = "PDF file is corrupted or empty"


class PasswordProtectedPDF(TechnicalValidationError):
    """The PDF is encrypted and requires a password to be read."""

    status_code = 422
    detail = "PDF file is password protected"


class UnsupportedFileFormat(TechnicalValidationError):
    """The file format is not one of the accepted PDF/JPEG/PNG formats."""

    status_code = 422
    detail = "File format is not supported"


class InvalidImage(TechnicalValidationError):
    """The image cannot be loaded by the image processing library."""

    status_code = 422
    detail = "Image file is invalid"


class TechnicalValidationFailed(TechnicalValidationError):
    """The technical validation run failed catastrophically."""

    status_code = 500
    detail = "Technical validation failed unexpectedly"
