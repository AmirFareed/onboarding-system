"""Benchmark the PostgreSQL bulk queue with controlled mock processing.

Runs realistic batch sizes (10 / 40 / 80 / 160 documents) with 1-3 workers
against the real PostgreSQL database. Processing is a deterministic 10 ms mock
so OCR and AI resources are never touched. Also benchmarks stale-job recovery:
jobs claimed by a simulated crashed worker are recovered by
``recover_stale_processing``.

Usage (from the backend directory):

    .venv/bin/python scripts/benchmark_bulk_queue.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from app.bulk_queue.workers import drain_queue
from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models.application import Application
from app.database.models.document import Document
from app.database.models.enums import (
    DocumentProcessingStatus,
    DocumentType,
    JobStatus,
)
from app.database.models.queue_job import QueueJob
from app.database.repositories.queue_job_repository import QueueJobRepository


class BenchmarkProcessor:
    """Small deterministic workload that avoids OCR and AI resources."""

    def __init__(self, db):
        self.db = db

    def process_one(self, *, application_id: int, document_id: int):
        time.sleep(0.01)
        document = self.db.get(Document, document_id)
        document.processing_status = DocumentProcessingStatus.COMPLETED
        self.db.commit()
        from app.document_processing.schemas import DocumentProcessingResult, ProcessingOutcome

        return DocumentProcessingResult(
            document_id=document_id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.PROCESSED,
        )


def _create_application_with_documents(db, document_count: int, created_by: str) -> Application:
    """Create an application with ``document_count`` uploaded documents."""
    application = Application(created_by=created_by)
    db.add(application)
    db.flush()
    documents = [
        Document(
            application_id=application.id,
            document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
            copy_number=index + 1,
            original_filename=f"benchmark-{index + 1}.pdf",
            stored_file_path=f"benchmark/{application.id}/{index + 1}.pdf",
            file_type="application/pdf",
            processing_status=DocumentProcessingStatus.UPLOADED,
        )
        for index in range(document_count)
    ]
    db.add_all(documents)
    db.commit()
    return application


def run_batch(document_count: int, workers: int) -> dict[str, float | int]:
    """Drain one batch and report throughput, wait times and reliability counts."""
    db = SessionLocal()
    try:
        application = _create_application_with_documents(db, document_count, "queue-benchmark")
        QueueJobRepository(db).enqueue_uploaded_documents(
            application_id=application.id,
            max_attempts=get_settings().bulk_queue_max_attempts,
        )
    finally:
        db.close()

    started = time.perf_counter()
    summary = drain_queue(workers=workers, processor_factory=BenchmarkProcessor)
    elapsed = time.perf_counter() - started

    db = SessionLocal()
    try:
        jobs = list(
            db.query(QueueJob)
            .filter(QueueJob.application_id == application.id)
            .all()
        )
        waits = [
            (job.started_at - job.created_at).total_seconds()
            for job in jobs
            if job.started_at and job.created_at
        ]
    finally:
        db.close()

    return {
        "documents": document_count,
        "workers": workers,
        "elapsed_seconds": round(elapsed, 4),
        "documents_per_minute": round(summary.succeeded / elapsed * 60, 2),
        "average_queue_wait_seconds": round(sum(waits) / len(waits), 4),
        "worker_utilization_percent": round((document_count * 0.01) / (elapsed * workers) * 100, 2),
        "completed_jobs": summary.succeeded,
        "failed_jobs": summary.failed,
        "retries": summary.retried,
    }


def run_crash_recovery_benchmark(document_count: int) -> dict[str, float | int]:
    """Simulate crashed workers and measure stale-job recovery throughput.

    Every job is force-claimed into PROCESSING by a ``crashed-*`` worker with a
    one-hour-old ``started_at``, then ``recover_stale_processing`` is measured
    against the configured stale timeout (10 seconds).
    """
    db = SessionLocal()
    try:
        application = _create_application_with_documents(db, document_count, "queue-benchmark-crash")
        QueueJobRepository(db).enqueue_uploaded_documents(
            application_id=application.id,
            max_attempts=get_settings().bulk_queue_max_attempts,
        )
        jobs = list(QueueJobRepository(db).list_by_application(application.id))
        crashed_at = datetime.now(timezone.utc) - timedelta(hours=1)
        for index, job in enumerate(jobs):
            job.status = JobStatus.PROCESSING
            job.worker_id = f"crashed-{index}"
            job.started_at = crashed_at
        db.commit()
    finally:
        db.close()

    started = time.perf_counter()
    db = SessionLocal()
    try:
        recovered = QueueJobRepository(db).recover_stale_processing(stale_after_seconds=10)
    finally:
        db.close()
    elapsed = time.perf_counter() - started

    return {
        "stale_jobs": document_count,
        "recovered_jobs": recovered,
        "recovery_seconds": round(elapsed, 4),
        "recovered_per_second": round(recovered / elapsed, 2) if elapsed else 0,
    }


if __name__ == "__main__":
    results = [
        run_batch(size, workers)
        for size in (10, 40, 80, 160)
        for workers in (1, 2, 3)
    ]
    results.append(run_crash_recovery_benchmark(160))
    print(json.dumps(results, indent=2))
