"""Data normalization module.

Produces a deterministic canonical form for every verified extracted field of an
application and persists it as the field's normalized value, so downstream
business validation compares like-for-like values. The module is deliberately
independent of the document analysis and confidence modules: it only reads the
persisted extracted fields and never re-runs extraction or scoring.
"""

from app.normalization.constants import (
    NORMALIZATION_VERSION,
    NormalizationOutcome,
    NormalizationStatus,
)
from app.normalization.exceptions import (
    ApplicationNotFound,
    NoExtractedFields,
    NormalizationError,
)
from app.normalization.normalizers import NormalizerRegistry
from app.normalization.schemas import (
    NormalizationSummary,
    NormalizedFieldItem,
    NormalizedFieldRecord,
    NormalizeResponse,
)
from app.normalization.services import NormalizationService
from app.normalization.validators import is_verified_for_normalization

__all__ = [
    "NORMALIZATION_VERSION",
    "ApplicationNotFound",
    "NoExtractedFields",
    "NormalizationError",
    "NormalizationOutcome",
    "NormalizationService",
    "NormalizationStatus",
    "NormalizationSummary",
    "NormalizeResponse",
    "NormalizedFieldItem",
    "NormalizedFieldRecord",
    "NormalizerRegistry",
    "is_verified_for_normalization",
]
