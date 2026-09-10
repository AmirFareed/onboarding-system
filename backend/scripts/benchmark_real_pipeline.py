"""Benchmark the REAL document-processing pipeline (Phase 15F).

Runs the actual pipeline (technical validation -> routing -> PDF/text
extraction -> OCR -> analysis/field extraction -> AI gate) on representative
documents through the real PostgreSQL queue, with realistic document mixes
(50% scanned PDFs, 30% digital PDFs, 20% images).

Because a full 10/40/80 x 1/2/3 matrix with real PaddleOCR would take hours,
the benchmark is honest about the split:

* ``--real-probe`` measures the genuine per-page PaddleOCR cost once, on a
  rasterized text page (this is the dominant real cost).
* The matrix runs the REAL code paths (validation, PyMuPDF probing, page
  rendering, OpenCV preprocessing, analysis, queue claiming) but substitutes a
  calibrated fake OCR engine that sleeps the measured per-page cost, so queue
  overhead and non-OCR pipeline cost are measured accurately.
* A digital-only batch runs with zero OCR to show the no-OCR floor.

Usage (from the backend directory):

    PYTHONPATH=. .venv/bin/python scripts/benchmark_real_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pymupdf

from app.core.config import get_settings

# The development ``.env`` sets DEBUG=true, which would create the SQLAlchemy
# engine with ``echo=True`` and print every statement to stdout, corrupting the
# JSON report (the engine's own StreamHandler bypasses logger levels). Clear
# debug BEFORE ``app.database`` is imported so the engine is created without
# echo and the report stays clean and valid JSON.
get_settings().debug = False

from app.bulk_queue.workers import drain_queue
from app.database.connection import SessionLocal
from app.database.models.document import Document
from app.database.models.enums import DocumentProcessingStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.document_analysis.constants import AnalyzedDocumentType, EXPECTED_FIELDS
from app.document_analysis.fallbacks import AiFallbackMetrics
from app.document_analysis.services import DocumentAnalysisService
from app.document_processing import services as processing_services
from app.document_processing.processors import (
    OCRExtraction,
    PaddleOCREngine,
    preprocess_image,
)
from app.document_processing.services import DocumentProcessingService
from app.technical_validation.services import TechnicalValidationService
from app.upload.constants import DOCUMENT_TYPE_SLUGS

#: Canned OCR output used by the calibrated engine. Deliberately missing the
#: IBAN and transaction count so the scanned/image documents exercise the AI
#: fallback gate (fields_requiring_ai) without any AI provider being configured.
FAKE_OCR_TEXT = """MONTHLY ACCOUNT STATEMENT
Account Holder: John A. Doe
Account Number: 1234567890
Bank: Sparkasse
Statement Period: 01/01/2026 - 31/01/2026
Opening Balance: 1,250.50
Closing Balance: 3,200.75
Total Credits: 2,500.00
Total Debits: 549.75
Currency: EUR
"""

#: Full statement embedded in the digital PDFs so rule extraction resolves
#: every field without AI (proving digital documents never need the fallback).
FULL_BANK_TEXT = FAKE_OCR_TEXT.replace(
    "Currency: EUR\n", "Currency: EUR\nIBAN: DE89370400440532013000\nTransactions: 23\n"
)

BANK_LINES = FAKE_OCR_TEXT.splitlines()
FULL_BANK_LINES = FULL_BANK_TEXT.splitlines()


def make_digital_pdf_bytes(text_lines: list[str], pages: int = 2) -> bytes:
    """Build a digital PDF with real embedded text (extracted by PyMuPDF)."""
    document = pymupdf.open()
    for _ in range(pages):
        page = document.new_page(width=595, height=842)
        y = 72
        for line in text_lines:
            page.insert_text((72, y), line, fontsize=11)
            y += 20
    content = document.tobytes()
    document.close()
    return content


def render_text_image(
    lines: list[str] | None = None,
    *,
    fontsize: int = 26,
    scale: float = 2.0,
) -> np.ndarray:
    """Rasterize real text onto a synthetic page (genuine OCR-friendly image)."""
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    y = 90
    for line in lines or BANK_LINES:
        page.insert_text((72, y), line, fontsize=fontsize, fontname="helv")
        y += 80
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    samples = np.frombuffer(pixmap.samples, dtype=np.uint8)
    image = samples.reshape(pixmap.height, pixmap.width, pixmap.n)
    document.close()
    return image


def encode_png(image: np.ndarray) -> bytes:
    """Encode an image as PNG bytes."""
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return buffer.tobytes()


def make_scanned_pdf_bytes(image: np.ndarray) -> bytes:
    """Build an image-only (scanned) PDF from one page image."""
    document = pymupdf.open()
    page = document.new_page(width=400, height=566)
    page.insert_image(page.rect, stream=encode_png(image))
    content = document.tobytes()
    document.close()
    return content


def create_application(
    storage_root: Path,
    count: int,
    *,
    mix: tuple[float, float, float] = (0.5, 0.3, 0.2),
) -> int:
    """Create an application with a realistic document mix and return its id.

    Args:
        storage_root: Temporary storage root the files are written into.
        count: Number of documents.
        mix: Fractions of (scanned PDF, digital PDF, image) documents.

    Returns:
        The application id.
    """
    scanned_share, digital_share, _ = mix
    scanned = int(round(count * scanned_share))
    digital = int(round(count * digital_share))
    image_count = max(0, count - scanned - digital)

    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by="perf-benchmark")
        application_id = application.id
    finally:
        db.close()

    slugs = {
        "scan": DOCUMENT_TYPE_SLUGS[DocumentType.AUTHORITY_LETTER],
        "digital": DOCUMENT_TYPE_SLUGS[DocumentType.TRIPARTITE_AGREEMENT],
        "image": DOCUMENT_TYPE_SLUGS[DocumentType.ONE_LINK_LETTER],
    }
    documents = []
    for index in range(count):
        if index < scanned:
            doc_type, slug, content, mime, filename = (
                DocumentType.AUTHORITY_LETTER,
                slugs["scan"],
                make_scanned_pdf_bytes(render_text_image()),
                "application/pdf",
                "scan.pdf",
            )
        elif index < scanned + digital:
            doc_type, slug, content, mime, filename = (
                DocumentType.TRIPARTITE_AGREEMENT,
                slugs["digital"],
                make_digital_pdf_bytes(FULL_BANK_LINES),
                "application/pdf",
                "statement.pdf",
            )
        else:
            doc_type, slug, content, mime, filename = (
                DocumentType.ONE_LINK_LETTER,
                slugs["image"],
                encode_png(render_text_image()),
                "image/png",
                "statement.png",
            )
        folder = f"applications/APP-{application_id:06d}/{slug}"
        directory = Path(storage_root) / folder
        directory.mkdir(parents=True, exist_ok=True)
        storage_name = f"{uuid4().hex}{Path(filename).suffix}"
        (directory / storage_name).write_bytes(content)
        documents.append(
            Document(
                application_id=application_id,
                document_type=doc_type,
                copy_number=index + 1,
                original_filename=filename,
                stored_file_path=f"{folder}/{storage_name}",
                file_type=mime,
                processing_status=DocumentProcessingStatus.UPLOADED,
            )
        )
    db = SessionLocal()
    try:
        DocumentRepository(db).create_many(documents=documents)
    finally:
        db.close()
    return application_id


class CalibratedOcrEngine:
    """Fake OCR engine costing the measured real per-page time."""

    def __init__(self, per_page_seconds: float, text: str) -> None:
        self.per_page_seconds = per_page_seconds
        self.text = text
        self.calls = 0

    def extract(self, image) -> OCRExtraction:
        self.calls += 1
        if self.per_page_seconds > 0:
            time.sleep(self.per_page_seconds)
        return OCRExtraction(text=self.text, confidence=0.95)


class InstrumentedProcessor:
    """Timing wrapper around the real per-document processing service."""

    def __init__(self, db, timings: list[float]) -> None:
        self._inner = DocumentProcessingService(db)
        self._timings = timings

    def process_one(self, *, application_id: int, document_id: int):
        started = time.perf_counter()
        result = self._inner.process_one(
            application_id=application_id,
            document_id=document_id,
        )
        self._timings.append(time.perf_counter() - started)
        return result


def measure_real_ocr_per_page() -> tuple[float, int]:
    """Measure the genuine per-page PaddleOCR cost on a text image."""
    preprocessed = preprocess_image(render_text_image())
    engine = PaddleOCREngine()
    started = time.perf_counter()
    extraction = engine.extract(preprocessed)
    elapsed = time.perf_counter() - started
    return elapsed, len(extraction.text)


def run_batch(
    count: int,
    workers: int,
    *,
    storage_root: Path,
    ocr_sleep: float,
    expected_fields_total: int,
) -> dict[str, float | int | str]:
    """Run the real pipeline for one (documents, workers) combination."""
    timings: list[float] = []
    engine = CalibratedOcrEngine(ocr_sleep, FAKE_OCR_TEXT)
    processing_services.ocr_engine_factory = lambda: engine

    application_id = create_application(storage_root, count)

    db = SessionLocal()
    try:
        started = time.perf_counter()
        TechnicalValidationService(db).validate(application_id=application_id)
        validation_elapsed = time.perf_counter() - started
        QueueJobRepository(db).enqueue_uploaded_documents(
            application_id=application_id,
            max_attempts=3,
        )
    finally:
        db.close()

    started = time.perf_counter()
    summary = drain_queue(
        workers=workers,
        processor_factory=lambda db: InstrumentedProcessor(db, timings),
    )
    drain_elapsed = time.perf_counter() - started

    metrics = AiFallbackMetrics()
    db = SessionLocal()
    try:
        started = time.perf_counter()
        DocumentAnalysisService(db, metrics=metrics).analyze(application_id=application_id)
        analysis_elapsed = time.perf_counter() - started
        jobs = list(QueueJobRepository(db).list_by_application(application_id))
        waits = [
            (job.started_at - job.created_at).total_seconds()
            for job in jobs
            if job.started_at and job.created_at
        ]
    finally:
        db.close()

    processing_seconds = sum(timings)
    # Fraction of the available worker-time actually spent processing. At one
    # worker ``100% - utilization`` is the pure queue/claim overhead; with more
    # workers the remainder reflects idle capacity while documents wait in the
    # queue (reported separately as the average queue wait).
    utilization = min(100.0, processing_seconds / (drain_elapsed * workers) * 100)
    return {
        "documents": count,
        "workers": workers,
        "drain_elapsed_seconds": round(drain_elapsed, 3),
        "validation_seconds": round(validation_elapsed, 3),
        "analysis_seconds": round(analysis_elapsed, 3),
        "documents_per_minute": round(summary.succeeded / drain_elapsed * 60, 2),
        "average_document_processing_seconds": round(
            processing_seconds / len(timings), 4
        ),
        "worker_utilization_percent": round(utilization, 2),
        "average_queue_wait_seconds": round(sum(waits) / len(waits), 4),
        "ocr_calls": engine.calls,
        "ai_calls": metrics.ai_calls,
        "fields_requiring_ai": metrics.fields_requiring_ai,
        "ai_fallback_percent": round(
            metrics.fields_requiring_ai / expected_fields_total * 100, 2
        ),
        "completed": summary.succeeded,
        "failed": summary.failed,
        "retries": summary.retried,
    }


def run_digital_only_batch(
    count: int,
    workers: int,
    *,
    storage_root: Path,
) -> dict[str, float | int]:
    """Digital-PDF-only run: real PyMuPDF extraction, zero OCR calls."""
    timings: list[float] = []
    engine = CalibratedOcrEngine(0.0, "")
    processing_services.ocr_engine_factory = lambda: engine

    application_id = create_application(storage_root, count, mix=(0.0, 1.0, 0.0))
    db = SessionLocal()
    try:
        TechnicalValidationService(db).validate(application_id=application_id)
        QueueJobRepository(db).enqueue_uploaded_documents(
            application_id=application_id,
            max_attempts=3,
        )
    finally:
        db.close()

    started = time.perf_counter()
    summary = drain_queue(
        workers=workers,
        processor_factory=lambda db: InstrumentedProcessor(db, timings),
    )
    drain_elapsed = time.perf_counter() - started

    return {
        "documents": count,
        "workers": workers,
        "drain_elapsed_seconds": round(drain_elapsed, 3),
        "documents_per_minute": round(summary.succeeded / drain_elapsed * 60, 2),
        "average_document_processing_seconds": round(
            sum(timings) / len(timings), 4
        ),
        "ocr_calls": engine.calls,
        "completed": summary.succeeded,
        "failed": summary.failed,
        "retries": summary.retried,
    }


def cleanup_benchmark_applications() -> None:
    """Remove benchmark applications (cascade deletes their rows)."""
    db = SessionLocal()
    try:
        from sqlalchemy import text

        db.execute(text("DELETE FROM applications WHERE created_by = 'perf-benchmark'"))
        db.commit()
    finally:
        db.close()


def recommend_workers(real_ocr_per_page: float) -> tuple[int, str]:
    """Recommend a practical worker count for this machine.

    OCR is CPU-bound and PaddleOCR already uses several native threads per
    process, so per-process worker counts above 2-3 rarely help. The
    recommendation keeps one CPU core free for the API and caps concurrency at
    four; RAM is bounded because scanned pages are rendered lazily (one page
    per worker at a time, ~50-80 MB per active page).
    """
    cpu_count = os.cpu_count() or 2
    recommended = min(max(cpu_count // 2, 2), 4)
    reasoning = (
        f"{cpu_count} logical CPUs; OCR is CPU-bound and the engine is "
        f"multi-threaded per process; keep one core free and cap at 4 in-process "
        f"workers (see docs/phase15f-performance.md)."
    )
    return recommended, reasoning


def main() -> None:
    """Run the benchmark and print the JSON report."""
    parser = argparse.ArgumentParser(description="Phase 15F real-pipeline benchmark")
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 40, 80])
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument(
        "--ocr-sleep",
        type=float,
        default=0.2,
        help="Calibrated OCR seconds per page. The real per-page cost is "
        "measured separately and reported; the matrix uses this fixed value so "
        "queue overhead and non-OCR pipeline cost are measured at scale.",
    )
    parser.add_argument("--no-real-probe", action="store_true")
    args = parser.parse_args()

    # Keep the JSON report on stdout. The engine is created without echo (debug
    # was cleared before ``app.database`` was imported above); belt-and-suspenders
    # in case an echo engine already exists from an earlier import in this process.
    logging.getLogger("sqlalchemy.engine").disabled = True
    logging.getLogger("sqlalchemy.pool").disabled = True

    settings = get_settings()
    original_root = settings.upload_storage_root
    storage_root = Path(tempfile.mkdtemp(prefix="perf-benchmark-"))
    settings.upload_storage_root = storage_root

    results: list[dict] = []
    try:
        real_ocr_per_page = None
        if not args.no_real_probe:
            real_ocr_per_page, recognized = measure_real_ocr_per_page()
            print(
                f"# Real OCR probe: {real_ocr_per_page:.3f}s/page "
                f"({recognized} characters recognized)",
                file=sys.stderr,
            )
        ocr_sleep = args.ocr_sleep
        print(f"# Calibrated OCR sleep: {ocr_sleep:.3f}s/page", file=sys.stderr)

        expected_per_doc = len(EXPECTED_FIELDS[AnalyzedDocumentType.BANK_STATEMENT])
        for size in args.sizes:
            for workers in args.workers:
                row = run_batch(
                    size,
                    workers,
                    storage_root=storage_root,
                    ocr_sleep=ocr_sleep,
                    expected_fields_total=size * expected_per_doc,
                )
                results.append(row)
                print(
                    f"# {size} documents x {workers} worker(s): "
                    f"{row['drain_elapsed_seconds']}s, {row['documents_per_minute']} docs/min",
                    file=sys.stderr,
                )

        digital = run_digital_only_batch(40, 2, storage_root=storage_root)
        print(
            f"# Digital-only 40 x 2: {digital['drain_elapsed_seconds']}s, "
            f"{digital['ocr_calls']} OCR calls",
            file=sys.stderr,
        )
    finally:
        settings.upload_storage_root = original_root
        shutil.rmtree(storage_root, ignore_errors=True)
        cleanup_benchmark_applications()

    recommended, reasoning = recommend_workers(real_ocr_per_page or 0.1)
    peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = {
        "real_ocr_per_page_seconds": real_ocr_per_page,
        "calibrated_ocr_sleep_seconds": round(ocr_sleep, 4),
        "cpu_count": os.cpu_count(),
        "peak_rss_mb": round(peak_rss_kb / 1024, 1),
        "recommended_workers": recommended,
        "recommendation_reasoning": reasoning,
        "runs": results,
        "digital_only_batch": digital,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
