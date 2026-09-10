"""Continuous learning module.

Prepares the verified feedback recorded during document verification as a
clean, versioned, machine-learning-ready dataset. The module performs no
validation, OCR, normalization or human review of its own and contains no
training logic: it reads the field-level samples recorded by the confidence
scoring and final human verification phases, excludes incomplete or invalid
records, produces a deterministic SHA-256 digest, computes reproducible
statistics and exports the dataset as JSON or CSV for future OCR, extraction
and document-AI improvements.
"""

from app.continuous_learning.constants import (
    CL_PREFIX,
    CONTINUOUS_LEARNING_VERSION,
    EXPORT_FORMAT_CSV,
    EXPORT_FORMAT_JSON,
)
from app.continuous_learning.exceptions import (
    ContinuousLearningError,
    DatasetExportError,
    DatasetNotFound,
    DatasetValidationError,
)
from app.continuous_learning.routes import router
from app.continuous_learning.services import ContinuousLearningService

__all__ = [
    "CL_PREFIX",
    "CONTINUOUS_LEARNING_VERSION",
    "EXPORT_FORMAT_CSV",
    "EXPORT_FORMAT_JSON",
    "ContinuousLearningError",
    "ContinuousLearningService",
    "DatasetExportError",
    "DatasetNotFound",
    "DatasetValidationError",
    "router",
]
