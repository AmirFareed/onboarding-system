"""Phase 15F regression tests: OCR/AI are only invoked when necessary.

These tests pin the performance-safety guarantees of the real pipeline:

* digital PDFs never invoke OCR (embedded text is extracted with PyMuPDF);
* scanned PDFs invoke OCR exactly once per page;
* the queue worker processes each document exactly once;
* the rule/regex extraction pipeline never invokes AI;
* low-confidence (missing/invalid) fields invoke the AI fallback only for those
  fields, and only when a fallback provider is configured;
* a failing AI call is recorded and never breaks analysis.

Retry/recovery behaviour and progress consistency are covered by the Phase 15E
tests in ``tests/test_bulk_queue.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.bulk_queue.workers import BulkQueueWorker
from app.database.connection import SessionLocal
from app.database.models.document import Document
from app.database.models.enums import DocumentProcessingStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.document_analysis.constants import AnalyzedDocumentType
from app.document_analysis.services import DocumentAnalysisService
from app.document_processing import services as processing_services
from app.document_processing.constants import (
    PADDLE_OCR_ENGINE,
    PYMUPDF_ENGINE,
    ProcessingMethod,
)
from app.document_processing.processors import OCRExtraction
from app.document_processing.schemas import ProcessingOutcome
from app.document_processing.services import DocumentProcessingService
from tests.test_bulk_queue import authenticate
from tests.test_document_processing_api import (
    FakeOCREngine,
    make_scanned_pdf_bytes,
)
from tests.test_technical_validation_api import (
    add_document,
    create_application,
    make_document_image,
    make_valid_pdf_bytes,
    run_validation,
)

#: Representative bank statement whose every expected field extracts and
#: validates, so the rule pipeline resolves the document without any fallback.
FULL_BANK_STATEMENT = """MONTHLY ACCOUNT STATEMENT
Account Holder: John A. Doe
Account Number: 1234567890
IBAN: DE89370400440532013000
Bank: Sparkasse
Statement Period: 01/01/2026 - 31/01/2026
Opening Balance: 1,250.50
Closing Balance: 3,200.75
Total Credits: 2,500.00
Total Debits: 549.75
Currency: EUR
Transactions: 23
"""

#: Same statement with the IBAN and transaction count removed so the rule
#: pipeline leaves exactly those two expected fields unresolved.
PARTIAL_BANK_STATEMENT = """MONTHLY ACCOUNT STATEMENT
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


class FakeAiFallback:
    """Records invocations and resolves every requested field deterministically."""

    def __init__(self) -> None:
        self.calls: list[tuple[AnalyzedDocumentType, list[str]]] = []

    def resolve(self, *, document_type, text, fields, field_names):
        self.calls.append((document_type, sorted(field_names)))
        resolved = {}
        if "iban" in field_names:
            resolved["iban"] = "DE89370400440532013000"
        if "transaction_count" in field_names:
            resolved["transaction_count"] = 23
        return resolved


class ExplodingFallback:
    """Fallback provider that always fails."""

    def resolve(self, **kwargs):
        raise RuntimeError("AI outage")


def insert_analysis_fixture(ocr_text: str) -> tuple[int, int]:
    """Create an application, a completed document and its OCR text directly."""
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by="perf-safety")
        document = Document(
            application_id=application.id,
            document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
            copy_number=1,
            original_filename="statement.pdf",
            stored_file_path="unused.pdf",
            file_type="application/pdf",
            processing_status=DocumentProcessingStatus.COMPLETED,
        )
        db.add(document)
        db.flush()
        OCRRepository(db).upsert(
            document_id=document.id,
            raw_ocr_text=ocr_text,
            ocr_engine=PYMUPDF_ENGINE,
            processing_time_ms=1,
            overall_confidence=None,
            processing_method=ProcessingMethod.PYMUFPDF_TEXT_EXTRACTION.value,
            page_count=1,
            character_count=len(ocr_text),
            processed_at=datetime.now(timezone.utc),
        )
        db.commit()
        return application.id, document.id
    finally:
        db.close()


def analyze_application(
    application_id: int,
    *,
    fallback_factory=None,
):
    """Run the analysis service over an application and return response + metrics."""
    db = SessionLocal()
    try:
        service = DocumentAnalysisService(db, fallback_factory=fallback_factory)
        return service.analyze(application_id=application_id), service.metrics
    finally:
        db.close()


def process_one_document(application_id: int, document_id: int):
    """Run the queue's per-document processing entry point on one document."""
    db = SessionLocal()
    try:
        return DocumentProcessingService(db).process_one(
            application_id=application_id,
            document_id=document_id,
        )
    finally:
        db.close()


# --- OCR is only invoked when necessary -------------------------------------


def test_digital_pdf_never_invokes_ocr_through_queue_worker(
    client, storage_root, monkeypatch
):
    authenticate(client)
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(pages=2, lines_per_page=10),
        "application/pdf",
    )
    run_validation(client, application_id)
    engine = FakeOCREngine()
    monkeypatch.setattr(processing_services, "ocr_engine_factory", lambda: engine)

    db = SessionLocal()
    try:
        document = list(DocumentRepository(db).get_all_by_application(application_id))[0]
    finally:
        db.close()
    result = process_one_document(application_id, document.id)

    assert result.outcome is ProcessingOutcome.PROCESSED
    assert result.ocr_engine == PYMUPDF_ENGINE
    assert result.processing_method is ProcessingMethod.PYMUFPDF_TEXT_EXTRACTION
    assert engine.calls == 0, "digital PDFs must bypass OCR entirely"


def test_scanned_pdf_invokes_ocr_exactly_once_per_page(client, storage_root, monkeypatch):
    authenticate(client)
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.AUTHORITY_LETTER,
        "scan.pdf",
        make_scanned_pdf_bytes(
            make_document_image(lines=6),
            make_document_image(lines=6),
        ),
        "application/pdf",
    )
    run_validation(client, application_id)
    engine = FakeOCREngine(texts=["first page text", "second page text"])
    monkeypatch.setattr(processing_services, "ocr_engine_factory", lambda: engine)

    db = SessionLocal()
    try:
        document = list(DocumentRepository(db).get_all_by_application(application_id))[0]
    finally:
        db.close()
    result = process_one_document(application_id, document.id)

    assert result.outcome is ProcessingOutcome.PROCESSED
    assert result.ocr_engine == PADDLE_OCR_ENGINE
    assert result.page_count == 2
    assert "first page text" in result.raw_text
    assert "second page text" in result.raw_text
    assert engine.calls == 2, "each scanned page is OCR'd exactly once"


def test_queue_worker_processes_each_document_exactly_once(
    client, storage_root, monkeypatch
):
    authenticate(client)
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.AUTHORITY_LETTER,
        "scan.pdf",
        make_scanned_pdf_bytes(
            make_document_image(lines=6),
            make_document_image(lines=6),
        ),
        "application/pdf",
    )
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(pages=2, lines_per_page=5),
        "application/pdf",
    )
    run_validation(client, application_id)
    engine = FakeOCREngine(texts=["scanned page a", "scanned page b"])
    monkeypatch.setattr(processing_services, "ocr_engine_factory", lambda: engine)

    db = SessionLocal()
    try:
        _, created, _ = QueueJobRepository(db).enqueue_uploaded_documents(
            application_id=application_id,
            max_attempts=3,
        )
        assert created == 2
    finally:
        db.close()

    first = BulkQueueWorker(processor_factory=DocumentProcessingService).run_until_empty()
    second = BulkQueueWorker(processor_factory=DocumentProcessingService).run_until_empty()

    assert first.succeeded == 3, (
        "the two DOCUMENT_OCR jobs plus the auto-enqueued APPLICATION_PIPELINE "
        "job (which runs analysis/confidence/normalization/rule-validation now "
        "that extraction succeeds on these document types)"
    )
    assert second.processed == 0, "completed documents must never be reprocessed"
    assert engine.calls == 2, "2 scanned pages OCR'd, digital PDF never"


def test_iter_pdf_pages_matches_render_pdf_pages(storage_root):
    storage_root.mkdir(parents=True, exist_ok=True)
    path = storage_root / "scan.pdf"
    path.write_bytes(
        make_scanned_pdf_bytes(
            make_document_image(lines=4),
            make_document_image(lines=4),
        )
    )
    from app.document_processing.utils import iter_pdf_pages, render_pdf_pages

    lazy = [page.shape for page in iter_pdf_pages(path, dpi=72)]
    eager = [page.shape for page in render_pdf_pages(path, dpi=72)]
    assert lazy == eager
    assert len(lazy) == 2


# --- AI stays a fallback -----------------------------------------------------


def test_successful_rule_extraction_never_invokes_ai():
    application_id, _ = insert_analysis_fixture(FULL_BANK_STATEMENT)
    response, metrics = analyze_application(
        application_id,
        fallback_factory=lambda: FakeAiFallback(),
    )

    assert response.total_analyzed == 1
    item = response.items[0]
    assert item.verification_status == "VERIFIED"
    assert metrics.ai_calls == 0, "fully-resolved documents never touch AI"
    assert metrics.fields_requested == 0
    assert metrics.fields_requiring_ai == 0
    assert item.extracted_fields["iban"] == "DE89370400440532013000"


def test_low_confidence_fields_invoke_ai_only_for_those_fields():
    application_id, _ = insert_analysis_fixture(PARTIAL_BANK_STATEMENT)
    fallback = FakeAiFallback()
    response, metrics = analyze_application(
        application_id,
        fallback_factory=lambda: fallback,
    )

    assert response.total_analyzed == 1
    item = response.items[0]
    assert metrics.ai_calls == 1, "one provider invocation per document"
    assert metrics.fields_requiring_ai == 2
    assert metrics.fields_requested == 2
    assert metrics.fields_resolved == 2
    assert fallback.calls == [
        (AnalyzedDocumentType.BANK_STATEMENT, ["iban", "transaction_count"])
    ], "only the unresolved fields are sent to AI"
    assert item.extracted_fields["iban"] == "DE89370400440532013000"
    assert item.extracted_fields["transaction_count"] == 23
    statuses = {v.field: v.status for v in item.validation_results}
    assert statuses["iban"] == "valid", "validations are recomputed after merging"


def test_ai_fallback_disabled_by_default_makes_no_calls(monkeypatch):
    from app.document_analysis import services as analysis_services

    monkeypatch.setattr(analysis_services, "ai_fallback_factory", None)
    application_id, _ = insert_analysis_fixture(PARTIAL_BANK_STATEMENT)
    response, metrics = analyze_application(application_id)

    assert response.total_analyzed == 1
    assert metrics.ai_calls == 0, "no provider configured -> zero AI calls"
    assert metrics.fields_requested == 0
    assert metrics.fields_requiring_ai == 2, "the gate still measures the gap"
    assert response.items[0].extracted_fields.get("iban") is None


def test_ai_correction_of_invalid_field_is_applied():
    """An invalid-but-present field corrected by AI is merged and revalidated."""
    text = FULL_BANK_STATEMENT.replace(
        "DE89370400440532013000", "DE00000000000000000000"
    )
    application_id, _ = insert_analysis_fixture(text)
    fallback = FakeAiFallback()
    response, metrics = analyze_application(
        application_id,
        fallback_factory=lambda: fallback,
    )

    assert response.total_analyzed == 1
    item = response.items[0]
    assert metrics.ai_calls == 1
    assert metrics.fields_requiring_ai == 1
    assert metrics.fields_resolved == 1, "AI corrections of invalid fields count as resolved"
    assert item.extracted_fields["iban"] == "DE89370400440532013000"
    statuses = {v.field: v.status for v in item.validation_results}
    assert statuses["iban"] == "valid"


def test_failed_ai_call_is_recorded_and_analysis_continues():
    application_id, _ = insert_analysis_fixture(PARTIAL_BANK_STATEMENT)
    response, metrics = analyze_application(
        application_id,
        fallback_factory=lambda: ExplodingFallback(),
    )

    assert response.total_analyzed == 1, "AI failure must never break analysis"
    assert metrics.ai_calls == 1
    assert metrics.failed_calls == 1
    assert metrics.fields_resolved == 0
    assert response.items[0].outcome == "ANALYZED"


def test_fallback_values_are_gated_to_requested_fields():
    from app.document_analysis.fallbacks import merge_fallback_values

    merged = merge_fallback_values(
        {"account_holder": "John A. Doe"},
        {"iban": None, "bank_name": "EVIL", "transaction_count": 23},
        ["iban", "transaction_count"],
    )
    assert merged == {"account_holder": "John A. Doe", "transaction_count": 23}


@pytest.mark.integration
def test_paddleocr_engine_singleton_is_reused():
    """The OCR engine singleton is shared across every engine instance."""
    pytest.importorskip("paddleocr")
    from app.document_processing.processors import PaddleOCREngine

    first = PaddleOCREngine()
    second = PaddleOCREngine()
    assert first._engine is second._engine
