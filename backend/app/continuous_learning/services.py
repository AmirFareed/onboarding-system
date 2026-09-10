"""Continuous learning dataset service.

``ContinuousLearningService`` turns the verified feedback recorded during the
confidence and final human verification phases into a clean, versioned,
machine-learning-ready dataset. It reads every feedback sample, excludes
incomplete or invalid records, resolves document types, produces a
deterministic SHA-256 digest of the curated content, computes reproducible
statistics and exports the dataset as JSON or CSV.

The module deliberately contains no training logic: no model training,
fine-tuning, automatic retraining, scheduling or background jobs. It only
prepares labelled samples for future OCR, extraction and document-AI
improvements.
"""

import hashlib
import json
import logging
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import __version__
from app.continuous_learning.constants import (
    CL_PREFIX,
    CONTINUOUS_LEARNING_VERSION,
    CSV_COLUMNS,
    EXPORT_FORMAT_CSV,
    EXPORT_FORMAT_JSON,
    EXPORT_PREFIX,
    HASH_LENGTH,
    UNKNOWN_DECISION,
)
from app.continuous_learning.exceptions import DatasetExportError, DatasetNotFound
from app.continuous_learning.repositories import FeedbackRepository
from app.continuous_learning.schemas import (
    DatasetMetadata,
    DatasetStatistics,
    ExportResponse,
    LearningDataset,
    LearningDatasetEntry,
)
from app.continuous_learning.validators import (
    build_csv,
    build_record,
    compute_completeness,
    confidence_bucket,
    duplicate_signature,
    reviewer_label,
    validation_issue,
)

logger = logging.getLogger(__name__)


class ContinuousLearningService:
    """Read, curate, version and export the learning dataset.

    Args:
        db: Active database session.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._feedback = FeedbackRepository(db)

    # -- Public API -----------------------------------------------------------

    def get_dataset(self) -> LearningDataset:
        """Return the curated dataset together with its metadata.

        Raises:
            DatasetNotFound: When no valid records can be curated.
        """
        records, _, metadata = self._curate()
        if not records:
            raise DatasetNotFound()
        logger.info(
            "Continuous learning dataset generated: records=%s version=%s",
            metadata.record_count,
            metadata.dataset_version,
        )
        return LearningDataset(
            metadata=metadata,
            records=[LearningDatasetEntry(**record) for record in records],
        )

    def get_version(self) -> DatasetMetadata:
        """Return the current dataset metadata.

        Raises:
            DatasetNotFound: When no valid records can be curated.
        """
        _, _, metadata = self._curate()
        if metadata.record_count == 0:
            raise DatasetNotFound()
        return metadata

    def get_statistics(self) -> DatasetStatistics:
        """Aggregate deterministic statistics over the curated dataset.

        Raises:
            DatasetNotFound: When no valid records can be curated.
        """
        records, reviewers, metadata = self._curate()
        if not records:
            raise DatasetNotFound()
        logger.info("Continuous learning statistics generation started")
        confidence_values = [record["confidence_score"] for record in records]
        document_distribution = Counter(record["document_type"] for record in records)
        field_distribution = Counter(record["field_name"] for record in records)
        correction_distribution = Counter(
            record["decision"] if record["decision"] else UNKNOWN_DECISION
            for record in records
        )
        confidence_distribution = Counter(
            confidence_bucket(record["confidence_score"]) for record in records
        )
        reviewer_distribution = Counter(reviewers)
        statistics = DatasetStatistics(
            total_records=len(records),
            document_distribution=dict(sorted(document_distribution.items())),
            field_distribution=dict(sorted(field_distribution.items())),
            correction_distribution=dict(sorted(correction_distribution.items())),
            confidence_distribution=dict(sorted(confidence_distribution.items())),
            average_confidence=sum(confidence_values) / len(confidence_values),
            reviewer_distribution=dict(sorted(reviewer_distribution.items())),
            dataset_completeness=compute_completeness(records, reviewers),
            metadata=metadata,
        )
        logger.info(
            "Continuous learning statistics generated: records=%s",
            metadata.record_count,
        )
        return statistics

    def export_json(self) -> ExportResponse:
        """Export the curated dataset as a JSON array.

        Raises:
            DatasetNotFound: When no valid records can be curated.
            DatasetExportError: When the dataset cannot be serialized.
        """
        return self._export(EXPORT_FORMAT_JSON)

    def export_csv(self) -> ExportResponse:
        """Export the curated dataset as CSV text.

        Raises:
            DatasetNotFound: When no valid records can be curated.
            DatasetExportError: When the dataset cannot be serialized.
        """
        return self._export(EXPORT_FORMAT_CSV)

    # -- Internals ------------------------------------------------------------

    def _export(self, export_format: str) -> ExportResponse:
        records, _, metadata = self._curate()
        if not records:
            raise DatasetNotFound()
        logger.info(
            "Continuous learning dataset export started: format=%s", export_format
        )
        try:
            if export_format == EXPORT_FORMAT_JSON:
                content = json.dumps(records)
            else:
                content = build_csv(records, CSV_COLUMNS)
            response = ExportResponse(
                dataset_version=metadata.dataset_version,
                created_at=datetime.now(UTC),
                record_count=metadata.record_count,
                format=export_format,
                dataset_hash=metadata.dataset_hash,
                project_version=metadata.project_version,
                filename=f"{EXPORT_PREFIX}_{datetime.now(UTC):%Y%m%d_%H%M%S}.{export_format}",
                content=content,
            )
        except DatasetExportError:
            raise
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("Continuous learning dataset export failed")
            raise DatasetExportError() from exc
        logger.info(
            "Continuous learning dataset export completed: format=%s records=%s",
            export_format,
            metadata.record_count,
        )
        return response

    def _curate(self) -> tuple[list[dict], list[str], DatasetMetadata]:
        """Read, validate and version the curated dataset.

        Returns:
            A tuple of the canonical record dictionaries (ordered by dataset
            id), the aligned reviewer labels, and the dataset metadata.
        """
        rows = self._feedback.all_matching()
        logger.info(
            "Continuous learning dataset generation started: source_rows=%s",
            len(rows),
        )
        document_types = self._document_type_map(rows)
        ordered = sorted(rows, key=lambda row: row.id)
        seen_signatures: set[tuple] = set()
        records: list[dict] = []
        reviewers: list[str] = []
        excluded: Counter[str] = Counter()
        duplicates = 0
        for entry in ordered:
            signature = duplicate_signature(entry)
            if signature in seen_signatures:
                duplicates += 1
                continue
            seen_signatures.add(signature)
            issue = validation_issue(entry)
            if issue is not None:
                excluded[issue] += 1
                continue
            records.append(build_record(entry, document_types))
            reviewers.append(reviewer_label(entry))
        ordered_records = sorted(
            zip(records, reviewers, strict=False),
            key=lambda pair: pair[0]["human_corrected_value"],
        )
        records = [record for record, _ in ordered_records]
        reviewers = [reviewer for _, reviewer in ordered_records]
        metadata = self._metadata(records)
        logger.info(
            "Continuous learning dataset validation: valid=%s excluded=%s duplicates=%s reasons=%s",
            len(records),
            sum(excluded.values()),
            duplicates,
            dict(excluded),
        )
        logger.info(
            "Continuous learning version created: version=%s hash=%s",
            metadata.dataset_version,
            metadata.dataset_hash,
        )
        return records, reviewers, metadata

    def _metadata(self, records: list[dict]) -> DatasetMetadata:
        """Build deterministic dataset metadata from the curated records."""
        response_records = [
            LearningDatasetEntry(**record).model_dump(mode="json")
            for record in records
        ]
        content_hash = hashlib.sha256(
            json.dumps(
                response_records,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return DatasetMetadata(
            dataset_version=(
                f"{CL_PREFIX}-{CONTINUOUS_LEARNING_VERSION}-"
                f"{content_hash[:HASH_LENGTH]}"
            ),
            project_version=__version__,
            created_at=datetime.now(UTC),
            record_count=len(records),
            dataset_hash=content_hash,
        )

    def _document_type_map(self, rows) -> dict:
        """Map the row document ids to their document-type labels."""
        document_ids = [row.document_id for row in rows if row.document_id is not None]
        return self._feedback.document_types(document_ids)
