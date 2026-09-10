"""Feedback dataset service.

``FeedbackService`` centralizes the feedback produced by the document
verification pipeline: it reads the samples recorded by the confidence scoring
and final human verification phases, applies the requested filters, computes
deterministic statistics and exports the matching population as JSON or CSV.

The module is read-mostly by design. It performs no OCR, no normalization, no
rule validation and no human review -- every statistic and export is derived
from rows that earlier phases already persisted, so the aggregation is
reproducible for the same dataset and filters.
"""

import json
import logging
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.feedback.constants import (
    CSV_COLUMNS,
    EXPORT_FORMAT_CSV,
    EXPORT_FORMAT_JSON,
    TOP_N_FIELDS,
    UNKNOWN_DECISION,
    UNKNOWN_DOCUMENT_TYPE,
    UNKNOWN_REVIEWER,
)
from app.feedback.exceptions import ExportFailed, FeedbackNotFound
from app.feedback.repositories import FeedbackRepository
from app.feedback.schemas import (
    DailyFrequency,
    ExportResponse,
    FeedbackEntry,
    FeedbackFilters,
    FeedbackStatistics,
    FeedbackSummary,
    FieldCount,
)
from app.feedback.validators import (
    build_csv,
    document_type_label,
    ensure_aware,
    entry_to_dict,
    to_repository_filters,
    validate_filters,
)

logger = logging.getLogger(__name__)


class FeedbackService:
    """Read, aggregate and export the feedback dataset.

    Args:
        db: Active database session.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._feedback = FeedbackRepository(db)

    # -- Public API -----------------------------------------------------------

    def list_feedback(
        self,
        *,
        filters: FeedbackFilters,
        offset: int,
        limit: int,
    ) -> FeedbackSummary:
        """Return a paginated, filtered slice of the feedback dataset.

        Args:
            filters: Query filters applied with AND semantics.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            The requested page together with the total matching count.
        """
        validate_filters(filters)
        self._log_filters(filters)
        keyword_args = self._repository_arguments(filters)
        total = self._feedback.count_matching(**keyword_args)
        logger.info(
            "Feedback dataset retrieval: total=%s offset=%s limit=%s",
            total,
            offset,
            limit,
        )
        rows = self._feedback.list_matching(
            **keyword_args,
            offset=offset,
            limit=limit,
        )
        entries = [FeedbackEntry(**entry_to_dict(row)) for row in rows]
        return FeedbackSummary(
            total=total,
            offset=offset,
            limit=limit,
            returned=len(entries),
            items=entries,
        )

    def get_feedback(self, *, feedback_id: int) -> FeedbackEntry:
        """Return a single feedback entry by its dataset id.

        Args:
            feedback_id: Primary key of the entry.

        Returns:
            The feedback entry.

        Raises:
            FeedbackNotFound: When no entry has the given id.
        """
        row = self._feedback.get_by_id(feedback_id)
        if row is None:
            raise FeedbackNotFound()
        logger.info("Feedback entry retrieved: id=%s", feedback_id)
        return FeedbackEntry(**entry_to_dict(row))

    def get_statistics(self, *, filters: FeedbackFilters) -> FeedbackStatistics:
        """Aggregate deterministic statistics over the matching population.

        Args:
            filters: Query filters applied with AND semantics.

        Returns:
            The aggregated statistics for the filtered dataset.
        """
        validate_filters(filters)
        self._log_filters(filters)
        logger.info("Feedback statistics generation started")
        rows = self._feedback.all_matching(**self._repository_arguments(filters))
        generated_at = datetime.now(UTC)

        corrected = sum(
            1 for row in rows if (row.human_value or "") != (row.ocr_value or "")
        )
        field_counts = Counter(row.field_name for row in rows)
        most_corrected = [
            FieldCount(field_name=field_name, count=count)
            for field_name, count in sorted(
                field_counts.items(), key=lambda item: (-item[1], item[0])
            )[:TOP_N_FIELDS]
        ]
        confidence_values = [
            row.confidence_score for row in rows if row.confidence_score is not None
        ]
        average_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else None
        )
        by_reviewer = Counter(
            row.reviewer if row.reviewer else UNKNOWN_REVIEWER for row in rows
        )
        document_types = self._document_type_map(rows)
        by_document_type = Counter(
            document_types.get(row.document_id, UNKNOWN_DOCUMENT_TYPE) for row in rows
        )
        by_decision = Counter(
            row.decision if row.decision else UNKNOWN_DECISION for row in rows
        )
        daily = Counter(
            ensure_aware(row.recorded_at).astimezone(UTC).date() for row in rows
        )
        frequency = [
            DailyFrequency(date=day, count=count)
            for day, count in sorted(daily.items())
        ]

        statistics = FeedbackStatistics(
            total_entries=len(rows),
            total_corrected_fields=corrected,
            most_corrected_fields=most_corrected,
            average_confidence=average_confidence,
            corrections_by_reviewer=dict(sorted(by_reviewer.items())),
            corrections_by_document_type=dict(sorted(by_document_type.items())),
            corrections_by_decision=dict(sorted(by_decision.items())),
            correction_frequency=frequency,
            generated_at=generated_at,
        )
        logger.info(
            "Feedback statistics generated: entries=%s corrected=%s",
            len(rows),
            corrected,
        )
        return statistics

    def export_json(self, *, filters: FeedbackFilters) -> ExportResponse:
        """Export the matching population as a JSON array.

        Args:
            filters: Query filters applied with AND semantics.

        Returns:
            The export metadata with the JSON payload embedded.

        Raises:
            ExportFailed: When the dataset cannot be serialized.
        """
        return self._export(filters=filters, export_format=EXPORT_FORMAT_JSON)

    def export_csv(self, *, filters: FeedbackFilters) -> ExportResponse:
        """Export the matching population as CSV text.

        Args:
            filters: Query filters applied with AND semantics.

        Returns:
            The export metadata with the CSV payload embedded.

        Raises:
            ExportFailed: When the dataset cannot be serialized.
        """
        return self._export(filters=filters, export_format=EXPORT_FORMAT_CSV)

    # -- Internals ------------------------------------------------------------

    def _export(
        self,
        *,
        filters: FeedbackFilters,
        export_format: str,
    ) -> ExportResponse:
        validate_filters(filters)
        self._log_filters(filters)
        logger.info(
            "Feedback dataset export started: format=%s", export_format
        )
        try:
            rows = self._feedback.all_matching(
                **self._repository_arguments(filters)
            )
            records = [self._export_row(row) for row in rows]
            generated_at = datetime.now(UTC)
            if export_format == EXPORT_FORMAT_JSON:
                content = json.dumps(records)
            else:
                content = build_csv(records, CSV_COLUMNS)
            response = ExportResponse(
                format=export_format,
                filename=self._filename(export_format, generated_at),
                record_count=len(records),
                generated_at=generated_at,
                content=content,
            )
        except ExportFailed:
            raise
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("Feedback dataset export failed")
            raise ExportFailed() from exc
        logger.info(
            "Feedback dataset export completed: format=%s records=%s",
            export_format,
            response.record_count,
        )
        return response

    @staticmethod
    def _export_row(row) -> dict:
        """Serialize a row for export with an ISO-8601 timestamp."""
        record = entry_to_dict(row)
        record["recorded_at"] = ensure_aware(row.recorded_at).isoformat()
        return record

    @staticmethod
    def _filename(export_format: str, generated_at: datetime) -> str:
        return f"feedback_{generated_at:%Y%m%d_%H%M%S}.{export_format}"

    @staticmethod
    def _repository_arguments(filters: FeedbackFilters) -> dict:
        arguments = to_repository_filters(filters)
        if arguments["date_from"] is not None:
            arguments["date_from"] = ensure_aware(arguments["date_from"])
        if arguments["date_to"] is not None:
            arguments["date_to"] = ensure_aware(arguments["date_to"])
        return arguments

    @staticmethod
    def _log_filters(filters: FeedbackFilters) -> None:
        """Log the active filters so every read is traceable."""
        active = [
            f"{name}={value}"
            for name, value in filters.model_dump().items()
            if value is not None
        ]
        if active:
            logger.info("Feedback filter execution: %s", ", ".join(active))

    def _document_type_map(self, rows) -> dict:
        """Map the row document ids to their document-type labels."""
        document_ids = [row.document_id for row in rows if row.document_id is not None]
        return {
            document_id: document_type_label(document_type)
            for document_id, document_type in self._feedback.document_types(
                document_ids
            ).items()
        }
