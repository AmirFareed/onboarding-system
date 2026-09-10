"""Custom exceptions raised by the document analysis module.

Each exception carries an HTTP status code and a human-readable detail message,
mirroring the other modules' convention so the route layer can translate any
failure into a consistent, documented error response.
"""


class DocumentAnalysisError(Exception):
    """Base class for every document analysis module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Document analysis failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(DocumentAnalysisError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class OCRResultNotFound(DocumentAnalysisError):
    """No OCR/text extraction result exists for the document.

    Raised when analysis is requested for a document that has not been processed
    (or whose processing failed), because there is no text to analyse.
    """

    status_code = 404
    detail = "No OCR result found for the document; run document processing first"


class UnsupportedDocumentType(DocumentAnalysisError):
    """The extracted text does not match any known analysed document type."""

    status_code = 422
    detail = "Document type could not be determined from the extracted text"


class AnalysisFailed(DocumentAnalysisError):
    """The analysis pipeline failed to complete for a document."""

    status_code = 500
    detail = "Document analysis failed"


class ValidationFailed(DocumentAnalysisError):
    """A validation step rejected the analysis inputs."""

    status_code = 422
    detail = "Document validation failed during analysis"
