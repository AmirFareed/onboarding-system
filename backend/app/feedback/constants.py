"""Configuration for the feedback module.

Centralizes the module version, the correction-origin vocabulary, the export
formats and the deterministic statistics defaults. The module is read-mostly:
it reads, aggregates, exports and manages the feedback samples recorded by the
confidence scoring and final human verification phases, and never runs OCR,
normalization, rules or reviews itself.
"""

from app.database.models.enums import ReviewDecision

#: Version of the feedback dataset logic. Bumped whenever the dataset schema,
#: the export formats or the aggregation rules change so a consumer can trace
#: an exported dataset to the exact logic that produced it.
FEEDBACK_VERSION: str = "1.0.0"

# -- Correction origin --------------------------------------------------------
#: Correction was recorded by the low-confidence (per-field) human review.
ORIGIN_LOW_CONFIDENCE_REVIEW: str = "LOW_CONFIDENCE_REVIEW"
#: Correction was recorded by the final human review.
ORIGIN_FINAL_HUMAN_REVIEW: str = "FINAL_HUMAN_REVIEW"

#: Decision value stored for low-confidence-review corrections. The confidence
#: module uses its own enum value ``CORRECTED`` for the per-field decision.
DECISION_LOW_CONFIDENCE_CORRECTED: str = "CORRECTED"

#: Decisions recorded by the final human review.
FINAL_DECISIONS: tuple[ReviewDecision, ...] = (
    ReviewDecision.APPROVE,
    ReviewDecision.CORRECT,
    ReviewDecision.REJECT,
)

#: Every decision value that can appear in the dataset.
KNOWN_DECISIONS: tuple[str, ...] = (
    *[decision.value for decision in FINAL_DECISIONS],
    DECISION_LOW_CONFIDENCE_CORRECTED,
)

# -- Pagination ---------------------------------------------------------------
#: Default number of entries returned per page.
DEFAULT_LIMIT: int = 50
#: Upper bound for the page size so a single request cannot scan the dataset.
MAX_LIMIT: int = 500

# -- Statistics ---------------------------------------------------------------
#: Number of fields surfaced in ``most_corrected_fields``.
TOP_N_FIELDS: int = 10
#: Reviewer label used when a feedback entry carries no reviewer.
UNKNOWN_REVIEWER: str = "UNKNOWN"
#: Document-type label used when a feedback entry carries no document.
UNKNOWN_DOCUMENT_TYPE: str = "UNKNOWN"
#: Decision label used when a feedback entry carries no decision.
UNKNOWN_DECISION: str = "UNKNOWN"
#: Label used for corrections whose confidence score is missing.
UNKNOWN_CONFIDENCE: str = "UNKNOWN"

# -- Export -------------------------------------------------------------------
#: Identifier of the JSON export format.
EXPORT_FORMAT_JSON: str = "json"
#: Identifier of the CSV export format.
EXPORT_FORMAT_CSV: str = "csv"

#: Column order used for the CSV export; the exact 14 exposed fields.
CSV_COLUMNS: tuple[str, ...] = (
    "id",
    "application_id",
    "document_id",
    "ocr_result_id",
    "field_name",
    "original_ocr_value",
    "normalized_value",
    "human_corrected_value",
    "confidence_score",
    "confidence_source",
    "correction_reason",
    "reviewer",
    "decision",
    "origin",
    "recorded_at",
)


__all__ = [
    "CSV_COLUMNS",
    "DECISION_LOW_CONFIDENCE_CORRECTED",
    "DEFAULT_LIMIT",
    "EXPORT_FORMAT_CSV",
    "EXPORT_FORMAT_JSON",
    "FEEDBACK_VERSION",
    "FINAL_DECISIONS",
    "KNOWN_DECISIONS",
    "MAX_LIMIT",
    "ORIGIN_FINAL_HUMAN_REVIEW",
    "ORIGIN_LOW_CONFIDENCE_REVIEW",
    "TOP_N_FIELDS",
    "UNKNOWN_CONFIDENCE",
    "UNKNOWN_DECISION",
    "UNKNOWN_DOCUMENT_TYPE",
    "UNKNOWN_REVIEWER",
]
