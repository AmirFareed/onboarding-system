"""Custom exceptions raised by the upload module.

Each exception carries an HTTP status code so the exception handler in
:mod:`app.upload.routes` can translate any failure raised inside the module into
a consistent, documented error response.
"""


class UploadError(Exception):
    """Base class for every upload module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Upload operation failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class InvalidFileTypeException(UploadError):
    """The file content or extension is not an allowed document format."""

    status_code = 400
    detail = "Invalid file type or content"


class FileTooLargeException(UploadError):
    """The uploaded file exceeds the configured maximum size."""

    status_code = 413
    detail = "File exceeds the maximum allowed size"


class MissingFileException(UploadError):
    """No file was attached to the upload request."""

    status_code = 400
    detail = "No file was provided"


class UnsupportedDocumentTypeException(UploadError):
    """The requested document type is not supported by the pipeline."""

    status_code = 422
    detail = "Unsupported document type"


class ApplicationNotFoundException(UploadError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class DocumentNotFoundException(UploadError):
    """The referenced document does not exist."""

    status_code = 404
    detail = "Document not found"


class DuplicateDocumentException(UploadError):
    """An application already holds a document of the requested type."""

    status_code = 409
    detail = "A document of this type already exists for the application"


class StorageException(UploadError):
    """A filesystem operation against the storage backend failed."""

    status_code = 500
    detail = "Storage operation failed"
