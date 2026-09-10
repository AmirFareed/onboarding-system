"""Domain exceptions for the validation report module.

Every exception carries an HTTP status code and a human-readable detail; the
module's routes translate them into ``HTTPException`` responses via the shared
``_handle_report_errors`` decorator.
"""


class ReportError(Exception):
    """Base class for every validation report module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Report generation failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ApplicationNotFound(ReportError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class ReportGenerationFailed(ReportError):
    """The report could not be assembled from the stored data."""

    status_code = 500
    detail = "Report generation failed"


class InvalidReportRequest(ReportError):
    """The report request is malformed or not supported."""

    status_code = 400
    detail = "Invalid report request"
