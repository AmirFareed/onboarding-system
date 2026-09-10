"""Custom exceptions raised by the document processing module.

Each exception carries an HTTP status code and a human-readable detail message,
mirroring the other modules' convention so the route layer can translate any
failure into a consistent, documented error response.
"""


class DocumentProcessingError(Exception):
    """Base class for every document processing module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Document processing failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(DocumentProcessingError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class TechnicalValidationRequired(DocumentProcessingError):
    """No technical validation report exists for the application.

    Raised when processing is requested before Phase 5 technical validation has
    run, because documents cannot be safely routed without it.
    """

    status_code = 400
    detail = (
        "Technical validation must be run for the application before processing documents"
    )


class UnsupportedDocument(DocumentProcessingError):
    """The document format cannot be processed by the pipeline."""

    status_code = 422
    detail = "Document format is not supported for processing"


class CorruptedDocument(DocumentProcessingError):
    """The stored document file cannot be opened or read."""

    status_code = 422
    detail = "Document file is corrupted or unreadable"


class EmptyExtraction(DocumentProcessingError):
    """Text extraction produced no text for the document."""

    status_code = 422
    detail = "Text extraction produced no text for the document"


class OCRProcessingFailed(DocumentProcessingError):
    """The OCR engine failed to process the document."""

    status_code = 500
    detail = "OCR processing failed"


class ProcessingTimeout(DocumentProcessingError):
    """The per-document processing time budget was exceeded."""

    status_code = 504
    detail = "Document processing exceeded the time limit"
