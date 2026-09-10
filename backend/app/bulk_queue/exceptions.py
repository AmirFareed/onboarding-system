"""Domain exceptions for the bulk queue module."""


class BulkQueueError(Exception):
    """Base queue exception translated by the route layer."""

    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ApplicationNotFound(BulkQueueError):
    """Raised when an application does not exist."""

    def __init__(self) -> None:
        super().__init__("Application not found", status_code=404)
