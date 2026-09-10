"""Configuration for the continuous learning module.

Centralizes the dataset-schema version, the export formats, the confidence
distribution buckets and the curated record contract. The module is read-only:
it turns the verified feedback recorded during earlier phases into a clean,
versioned, machine-learning-ready dataset. No model training, fine-tuning or
retraining belongs here -- it only prepares labelled samples for future use.
"""

from app.feedback.constants import (
    KNOWN_DECISIONS,
    UNKNOWN_DECISION,
    UNKNOWN_DOCUMENT_TYPE,
    UNKNOWN_REVIEWER,
)

#: Version of the curated dataset schema. Bumped whenever the record layout,
#: the curation rules or the hashing contract change so a consumer can trace an
#: exported dataset to the exact logic that produced it.
CONTINUOUS_LEARNING_VERSION: str = "1.0.0"

#: Prefix used for the deterministic dataset version identifier.
CL_PREFIX: str = "cl"

#: Number of hash characters embedded in the dataset version identifier.
HASH_LENGTH: int = 12

#: Hash algorithm used for the dataset integrity digest.
HASH_ALGORITHM: str = "sha256"

# -- Export -------------------------------------------------------------------
#: Identifier of the JSON export format.
EXPORT_FORMAT_JSON: str = "json"
#: Identifier of the CSV export format.
EXPORT_FORMAT_CSV: str = "csv"

#: Column order used for the CSV export; the exact curated record contract.
CSV_COLUMNS: tuple[str, ...] = (
    "application_id",
    "document_type",
    "field_name",
    "original_ocr_value",
    "normalized_value",
    "human_corrected_value",
    "confidence_score",
    "confidence_source",
    "correction_reason",
    "decision",
    "origin",
    "recorded_at",
)

# -- Confidence distribution ---------------------------------------------------
#: Deterministic buckets used for the confidence distribution. Upper bounds are
#: exclusive except the final bucket which is inclusive of 1.0.
CONFIDENCE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0.00-0.20", 0.0, 0.2),
    ("0.20-0.40", 0.2, 0.4),
    ("0.40-0.60", 0.4, 0.6),
    ("0.60-0.80", 0.6, 0.8),
    ("0.80-1.00", 0.8, 1.01),
)

# -- Completeness --------------------------------------------------------------
#: Optional record fields whose presence is reported in dataset completeness.
COMPLETENESS_FIELDS: tuple[str, ...] = (
    "document_type",
    "normalized_value",
    "confidence_source",
    "correction_reason",
    "decision",
    "origin",
    "reviewer",
)

# -- Filenames -----------------------------------------------------------------
#: Filename prefix used for curated dataset exports.
EXPORT_PREFIX: str = "continuous_learning_dataset"

__all__ = [
    "CL_PREFIX",
    "COMPLETENESS_FIELDS",
    "CONFIDENCE_BUCKETS",
    "CONTINUOUS_LEARNING_VERSION",
    "CSV_COLUMNS",
    "EXPORT_FORMAT_CSV",
    "EXPORT_FORMAT_JSON",
    "EXPORT_PREFIX",
    "HASH_ALGORITHM",
    "HASH_LENGTH",
    "KNOWN_DECISIONS",
    "UNKNOWN_DECISION",
    "UNKNOWN_DOCUMENT_TYPE",
    "UNKNOWN_REVIEWER",
]
