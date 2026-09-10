"""Domain exceptions for the continuous learning module.

Every exception carries an HTTP status code and a human-readable detail; the
module's routes translate them into ``HTTPException`` responses via the shared
``_handle_continuous_learning_errors`` decorator.
"""


class ContinuousLearningError(Exception):
    """Base class for every continuous learning module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Continuous learning module failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class DatasetNotFound(ContinuousLearningError):
    """The curated dataset holds no valid records."""

    status_code = 404
    detail = "Curated dataset is empty"


class DatasetValidationError(ContinuousLearningError):
    """The curated dataset failed its quality validation."""

    status_code = 422
    detail = "Curated dataset validation failed"


class DatasetExportError(ContinuousLearningError):
    """The curated dataset could not be exported."""

    status_code = 500
    detail = "Curated dataset export failed"
