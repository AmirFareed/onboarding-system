"""Pure helpers for the continuous learning module.

These functions carry no I/O: they validate a feedback sample against the
curated-dataset quality rules, build the canonical 12-field record, detect
duplicate signatures, map confidence scores into distribution buckets and
compute dataset completeness. Keeping them side-effect free makes the curation
pipeline and its statistics easy to test in isolation.
"""

import json
from collections import Counter

from app.continuous_learning.constants import (
    COMPLETENESS_FIELDS,
    CONFIDENCE_BUCKETS,
    KNOWN_DECISIONS,
    UNKNOWN_DOCUMENT_TYPE,
    UNKNOWN_REVIEWER,
)
from app.database.models.feedback_dataset import FeedbackEntry
from app.feedback.validators import (
    build_csv,
    document_type_label,
    ensure_aware,
)

#: Deterministic reasons a feedback sample is excluded from the curated set.
INVALID_MISSING_APPLICATION_ID = "missing_application_id"
INVALID_MISSING_FIELD_NAME = "missing_field_name"
INVALID_MISSING_OCR_VALUE = "missing_original_ocr_value"
INVALID_MISSING_HUMAN_VALUE = "missing_human_corrected_value"
INVALID_CONFIDENCE_SCORE = "invalid_confidence_score"
INVALID_DECISION = "invalid_decision"


def validation_issue(entry: FeedbackEntry) -> str | None:
    """Return the first quality-rule violation for a sample, or ``None``.

    A valid curated sample needs strict provenance: a source application, a
    field name, a non-empty OCR value, a non-empty human-corrected value and a
    confidence score within ``[0, 1]``. An unknown decision value also excludes
    the sample.
    """
    if entry.application_id is None:
        return INVALID_MISSING_APPLICATION_ID
    if not entry.field_name or not entry.field_name.strip():
        return INVALID_MISSING_FIELD_NAME
    if not entry.ocr_value or not entry.ocr_value.strip():
        return INVALID_MISSING_OCR_VALUE
    if not entry.human_value or not entry.human_value.strip():
        return INVALID_MISSING_HUMAN_VALUE
    score = entry.confidence_score
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return INVALID_CONFIDENCE_SCORE
    if not 0.0 <= numeric_score <= 1.0:
        return INVALID_CONFIDENCE_SCORE
    if entry.decision is not None and entry.decision not in KNOWN_DECISIONS:
        return INVALID_DECISION
    return None


def duplicate_signature(entry: FeedbackEntry) -> tuple:
    """Return a stable identity tuple for exact-duplicate detection.

    Two samples with the same application, document, field, OCR value, human
    value and recorded timestamp are considered duplicates; the lowest dataset
    id is kept.
    """
    return (
        entry.application_id,
        entry.document_id,
        entry.field_name,
        entry.ocr_value,
        entry.human_value,
        entry.recorded_at,
    )


def build_record(entry: FeedbackEntry, document_types: dict) -> dict:
    """Serialize one valid sample into the canonical 12-field record.

    Args:
        entry: The validated feedback sample.
        document_types: Mapping of document id to its ``DocumentType``; used to
            resolve the record's document type with an ``UNKNOWN`` fallback.

    Returns:
        The canonical record dictionary used for the dataset, its hash and its
        exports.
    """
    return {
        "application_id": entry.application_id,
        "document_type": document_type_label(
            document_types.get(entry.document_id)
        ),
        "field_name": entry.field_name,
        "original_ocr_value": entry.ocr_value,
        "normalized_value": entry.normalized_value,
        "human_corrected_value": entry.human_value,
        "confidence_score": float(entry.confidence_score),
        "confidence_source": entry.confidence_source,
        "correction_reason": entry.correction_reason,
        "decision": entry.decision,
        "origin": entry.origin,
        "recorded_at": ensure_aware(entry.recorded_at).isoformat(),
    }


def reviewer_label(entry: FeedbackEntry) -> str:
    """Return the reviewer label or the ``UNKNOWN`` fallback."""
    return entry.reviewer or UNKNOWN_REVIEWER


def confidence_bucket(score: float) -> str:
    """Map a validated confidence score to its distribution bucket label."""
    for label, lower, upper in CONFIDENCE_BUCKETS:
        if lower <= score < upper:
            return label
    return CONFIDENCE_BUCKETS[-1][0]  # pragma: no cover - scores are clamped


def canonical_records_json(records: list[dict]) -> str:
    """Serialize the curated records into the canonical hash input.

    Records must be passed in a fixed order (the curation pipeline sorts them by
    dataset id); ``sort_keys`` and fixed separators make the byte representation
    deterministic across calls and processes.
    """
    return json.dumps(
        records,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_completeness(
    records: list[dict], reviewers: list[str]
) -> dict[str, float]:
    """Compute the fraction of records carrying each optional field.

    A field counts as present when it is not null, not empty and (for the
    document type) not the ``UNKNOWN`` fallback. The reviewer presence comes
    from the aligned reviewer labels because reviewer names are not part of the
    exported record contract. Values are rounded to four decimal places.
    """
    total = len(records)
    if total == 0:
        return dict.fromkeys(COMPLETENESS_FIELDS, 0.0)
    presence: Counter[str] = Counter()
    for field in COMPLETENESS_FIELDS:
        for index, record in enumerate(records):
            if field == "reviewer":
                present = reviewers[index] != UNKNOWN_REVIEWER
            elif field == "document_type":
                present = record[field] != UNKNOWN_DOCUMENT_TYPE
            else:
                value = record[field]
                present = value is not None and value != ""
            if present:
                presence[field] += 1
    return {
        field: round(presence[field] / total, 4) for field in COMPLETENESS_FIELDS
    }


__all__ = [
    "INVALID_CONFIDENCE_SCORE",
    "INVALID_DECISION",
    "INVALID_MISSING_APPLICATION_ID",
    "INVALID_MISSING_FIELD_NAME",
    "INVALID_MISSING_HUMAN_VALUE",
    "INVALID_MISSING_OCR_VALUE",
    "build_csv",
    "build_record",
    "canonical_records_json",
    "compute_completeness",
    "confidence_bucket",
    "duplicate_signature",
    "ensure_aware",
    "reviewer_label",
    "validation_issue",
]
