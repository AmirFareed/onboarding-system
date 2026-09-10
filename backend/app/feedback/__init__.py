"""Feedback module.

Centralizes the feedback produced during document verification into a reusable,
structured dataset. The module performs no validation, OCR, normalization or
human review: it reads the field-level samples recorded by the confidence
scoring and final human verification phases, applies filters, computes
deterministic statistics and exports the dataset as JSON or CSV. The exports
are designed to feed future AI training / continuous-learning pipelines without
the module itself training or retraining any model.
"""

from app.feedback.constants import (
    DECISION_LOW_CONFIDENCE_CORRECTED,
    DEFAULT_LIMIT,
    EXPORT_FORMAT_CSV,
    EXPORT_FORMAT_JSON,
    FEEDBACK_VERSION,
    MAX_LIMIT,
    ORIGIN_FINAL_HUMAN_REVIEW,
    ORIGIN_LOW_CONFIDENCE_REVIEW,
    TOP_N_FIELDS,
    UNKNOWN_DECISION,
    UNKNOWN_DOCUMENT_TYPE,
    UNKNOWN_REVIEWER,
)
from app.feedback.exceptions import (
    ExportFailed,
    FeedbackError,
    FeedbackNotFound,
    InvalidFilter,
)
from app.feedback.routes import router
from app.feedback.services import FeedbackService

__all__ = [
    "DECISION_LOW_CONFIDENCE_CORRECTED",
    "DEFAULT_LIMIT",
    "EXPORT_FORMAT_CSV",
    "EXPORT_FORMAT_JSON",
    "FEEDBACK_VERSION",
    "MAX_LIMIT",
    "ORIGIN_FINAL_HUMAN_REVIEW",
    "ORIGIN_LOW_CONFIDENCE_REVIEW",
    "TOP_N_FIELDS",
    "UNKNOWN_DECISION",
    "UNKNOWN_DOCUMENT_TYPE",
    "UNKNOWN_REVIEWER",
    "ExportFailed",
    "FeedbackError",
    "FeedbackNotFound",
    "FeedbackService",
    "InvalidFilter",
    "router",
]
