"""Pure helpers for the feedback module.

These functions carry no I/O: they validate the filters, normalize datetimes,
serialize an entry into the canonical 14-field dictionary and build CSV text.
Keeping them side-effect free makes the aggregation and export logic easy to
test in isolation.
"""

import csv
import io
from datetime import UTC, datetime

from app.database.models.enums import DocumentType
from app.database.models.feedback_dataset import FeedbackEntry as FeedbackEntryModel
from app.feedback.constants import KNOWN_DECISIONS, UNKNOWN_DOCUMENT_TYPE
from app.feedback.exceptions import InvalidFilter
from app.feedback.schemas import FeedbackFilters


def validate_filters(filters: FeedbackFilters) -> FeedbackFilters:
    """Validate the semantic constraints of a filter combination.

    Raises:
        InvalidFilter: When the date range is inverted or the decision value is
            not part of the known decision vocabulary.
    """
    if (
        filters.date_from is not None
        and filters.date_to is not None
        and filters.date_from > filters.date_to
    ):
        raise InvalidFilter("date_from must not be after date_to")
    if filters.decision is not None and filters.decision not in KNOWN_DECISIONS:
        raise InvalidFilter(
            f"unknown decision {filters.decision!r}; "
            f"expected one of {', '.join(KNOWN_DECISIONS)}"
        )
    return filters


def to_repository_filters(filters: FeedbackFilters) -> dict:
    """Translate a filter model into keyword arguments for the repository.

    Document type and date ranges are passed through untouched (the repository
    resolves the document-type join); the decision is compared against the
    dataset vocabulary directly.
    """
    return {
        "application_id": filters.application_id,
        "reviewer": filters.reviewer,
        "document_type": filters.document_type,
        "field_name": filters.field_name,
        "decision": filters.decision,
        "date_from": filters.date_from,
        "date_to": filters.date_to,
        "min_confidence": filters.min_confidence,
    }


def ensure_aware(value: datetime) -> datetime:
    """Return a timezone-aware datetime, assuming UTC for naive inputs."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def entry_to_dict(entry: FeedbackEntryModel) -> dict:
    """Serialize one feedback entry into the canonical 14-field dictionary."""
    return {
        "id": entry.id,
        "application_id": entry.application_id,
        "document_id": entry.document_id,
        "ocr_result_id": entry.ocr_result_id,
        "field_name": entry.field_name,
        "original_ocr_value": entry.ocr_value,
        "normalized_value": entry.normalized_value,
        "human_corrected_value": entry.human_value,
        "confidence_score": entry.confidence_score,
        "confidence_source": entry.confidence_source,
        "correction_reason": entry.correction_reason,
        "reviewer": entry.reviewer,
        "decision": entry.decision,
        "origin": entry.origin,
        "recorded_at": entry.recorded_at,
    }


def build_csv(rows: list[dict], columns: tuple[str, ...]) -> str:
    """Serialize entry dictionaries into CSV text.

    Args:
        rows: Entry dictionaries with the canonical 14 fields.
        columns: Column order to emit; the first row is the header.

    Returns:
        The CSV payload as a string.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def document_type_label(document_type: DocumentType | None) -> str:
    """Return the canonical document-type label or ``UNKNOWN``."""
    return document_type.value if document_type is not None else UNKNOWN_DOCUMENT_TYPE
