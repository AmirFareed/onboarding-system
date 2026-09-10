"""Integration tests exercising the real PaddleOCR engine end to end.

These tests run the production extraction pipeline against the real OCR engine
(no engine substitution except in the failure-injection test, which needs a
deterministic mid-run failure). They cover all three routing paths -- digital
PDF -> PyMuPDF, scanned PDF -> PaddleOCR and image -> PaddleOCR -- plus OCR
result persistence and the guarantee that failed documents write no OCR rows.

The module is skipped automatically when PaddleOCR is not installed, so the
suite stays runnable on machines without the heavy dependencies.
"""

import numpy as np
import pymupdf
import pytest

pytest.importorskip("paddleocr")

from app.database.connection import SessionLocal
from app.database.models.enums import DocumentType
from app.database.repositories.ocr_repository import OCRRepository
from app.document_processing import processors
from app.document_processing.constants import (
    PADDLE_OCR_ENGINE,
    PYMUPDF_ENGINE,
    ProcessingMethod,
)
from app.document_processing.processors import PaddleOCREngine
from tests.test_bulk_queue import authenticate
from tests.test_document_processing_api import (
    get_ocr_results,
    make_scanned_pdf_bytes,
    patch_ocr_engine,
    process_documents,
)
from tests.test_technical_validation_api import (
    add_document,
    create_application,
    encode_png,
    make_valid_pdf_bytes,
    run_validation,
)

#: Distinctive machine-printed text the OCR engine must recognize.
OCR_LINES = [
    "ACME BANK LIMITED",
    "BANK STATEMENT",
    "Account Number 1234567890",
    "Opening Balance 5000.00",
    "Closing Balance 5250.00",
]

#: Tokens expected to survive recognition; matched against upper-cased text.
OCR_EXPECTED_TOKENS = ["ACME", "BANK", "1234567890"]


def render_text_image(
    lines: list[str] | None = None,
    *,
    fontsize: int = 30,
    scale: float = 3.0,
) -> np.ndarray:
    """Rasterize real text onto a synthetic page and return it as an image.

    PyMuPDF's built-in Helvetica needs no external font files, so the resulting
    image contains genuine, OCR-friendly printed text unlike the blank-line
    images produced by ``make_document_image``.

    Returns:
        An RGB image (height, width, 3) with the text rendered on it.
    """
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    y = 90
    for line in lines or OCR_LINES:
        page.insert_text((72, y), line, fontsize=fontsize, fontname="helv")
        y += 110
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    samples = np.frombuffer(pixmap.samples, dtype=np.uint8)
    image = samples.reshape(pixmap.height, pixmap.width, pixmap.n)
    document.close()
    return image


def install_pipeline_spies(monkeypatch) -> tuple[list[str], list[np.ndarray]]:
    """Record when preprocessing runs and what the engine receives.

    Wraps the production functions with delegating spies so the real pipeline
    runs unchanged while the test can assert the order of operations and that
    OCR receives the binary preprocessed image.

    Returns:
        A pair ``(order, captured_images)`` updated as the pipeline runs.
    """
    order: list[str] = []
    captured: list[np.ndarray] = []

    real_preprocess = processors.preprocess_image

    def spy_preprocess(image):
        order.append("preprocess")
        return real_preprocess(image)

    real_extract = PaddleOCREngine.extract

    def spy_extract(self, image):
        order.append("extract")
        captured.append(image)
        return real_extract(self, image)

    monkeypatch.setattr(processors, "preprocess_image", spy_preprocess)
    monkeypatch.setattr(PaddleOCREngine, "extract", spy_extract)
    return order, captured


def read_stored_rows(application_id: int) -> list:
    """Return the OCR result rows stored for an application."""
    db = SessionLocal()
    try:
        return list(OCRRepository(db).get_by_application(application_id))
    finally:
        db.close()


# --- Digital PDF route -------------------------------------------------------


@pytest.mark.integration
def test_digital_pdf_route_uses_pymupdf(client, storage_root, monkeypatch):
    authenticate(client)
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(pages=2, lines_per_page=5),
        "application/pdf",
    )
    run_validation(client, application_id)
    order, _ = install_pipeline_spies(monkeypatch)

    item = process_documents(client, application_id)["items"][0]

    assert item["outcome"] == "PROCESSED"
    assert item["ocr_engine"] == PYMUPDF_ENGINE
    assert item["processing_method"] == ProcessingMethod.PYMUFPDF_TEXT_EXTRACTION.value
    assert item["overall_confidence"] is None
    assert "Page 1 line 1" in item["raw_text"]
    assert order == [], "digital PDFs must not preprocess or call OCR"


# --- Scanned PDF route -------------------------------------------------------


@pytest.mark.integration
def test_scanned_pdf_route_uses_real_paddleocr(client, storage_root, monkeypatch):
    authenticate(client)
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        "scan.pdf",
        make_scanned_pdf_bytes(render_text_image()),
        "application/pdf",
    )
    run_validation(client, application_id)
    order, captured = install_pipeline_spies(monkeypatch)

    result = process_documents(client, application_id)
    item = result["items"][0]

    assert result["total_processed"] == 1
    assert result["total_failed"] == 0
    assert item["outcome"] == "PROCESSED"
    assert item["ocr_engine"] == PADDLE_OCR_ENGINE
    assert item["processing_method"] == ProcessingMethod.PADDLE_OCR.value
    assert item["overall_confidence"] is not None and item["overall_confidence"] > 0.5
    assert item["character_count"] > 0
    upper = item["raw_text"].upper()
    assert any(token in upper for token in OCR_EXPECTED_TOKENS), item["raw_text"]
    assert order == ["preprocess", "extract"], "OCR must follow preprocessing"
    assert len(captured) == 1
    assert captured[0].ndim == 2, "engine must receive the binary preprocessed image"

    stored = read_stored_rows(application_id)
    assert len(stored) == 1
    assert stored[0].ocr_engine == PADDLE_OCR_ENGINE
    assert stored[0].processing_method == ProcessingMethod.PADDLE_OCR.value
    assert stored[0].character_count == item["character_count"]
    assert stored[0].processed_at is not None


# --- Image route -------------------------------------------------------------


@pytest.mark.integration
def test_image_route_uses_real_paddleocr(client, storage_root, monkeypatch):
    authenticate(client)
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        "statement.png",
        encode_png(render_text_image()),
        "image/png",
    )
    run_validation(client, application_id)
    order, captured = install_pipeline_spies(monkeypatch)

    item = process_documents(client, application_id)["items"][0]

    assert item["outcome"] == "PROCESSED"
    assert item["ocr_engine"] == PADDLE_OCR_ENGINE
    assert item["processing_method"] == ProcessingMethod.PADDLE_OCR.value
    assert item["overall_confidence"] is not None and item["overall_confidence"] > 0.5
    upper = item["raw_text"].upper()
    assert any(token in upper for token in OCR_EXPECTED_TOKENS), item["raw_text"]
    assert order == ["preprocess", "extract"]
    assert captured[0].ndim == 2

    stored = read_stored_rows(application_id)
    assert len(stored) == 1
    assert stored[0].page_count == 1
    assert stored[0].character_count == item["character_count"]


# --- Persistence across all routes -------------------------------------------


@pytest.mark.integration
def test_mixed_application_persists_one_ocr_row_per_document(
    client, storage_root, monkeypatch
):
    authenticate(client)
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(),
        "application/pdf",
    )
    add_document(
        storage_root,
        application_id,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        "scan.pdf",
        make_scanned_pdf_bytes(render_text_image()),
        "application/pdf",
    )
    add_document(
        storage_root,
        application_id,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        "statement.png",
        encode_png(render_text_image()),
        "image/png",
    )
    run_validation(client, application_id)

    result = process_documents(client, application_id)

    assert result["total_processed"] == 3
    assert result["total_failed"] == 0
    assert {item["ocr_engine"] for item in result["items"]} == {
        PYMUPDF_ENGINE,
        PADDLE_OCR_ENGINE,
    }

    stored = get_ocr_results(client, application_id)
    assert stored["total"] == 3
    stored_by_document = {item["document_id"]: item for item in stored["items"]}
    for item in result["items"]:
        row = stored_by_document[item["document_id"]]
        assert row["raw_ocr_text"] == item["raw_text"]
        assert row["ocr_engine"] == item["ocr_engine"]
        assert row["processing_method"] == item["processing_method"]
        assert row["processed_at"] is not None

    rows = read_stored_rows(application_id)
    assert len(rows) == 3
    assert {row.ocr_engine for row in rows} == {PYMUPDF_ENGINE, PADDLE_OCR_ENGINE}
    assert all(row.character_count > 0 for row in rows)
    assert all(row.processed_at is not None for row in rows)


# --- Failure leaves no OCR row ------------------------------------------------


@pytest.mark.integration
def test_processing_failure_writes_no_ocr_row(client, storage_root, monkeypatch):
    """A failed document must not persist any OCR result.

    The engine is substituted with a deterministic failing one here: provoking a
    genuine mid-run engine error is environment dependent, and the persistence
    invariant under failure is what is under test. Everything else (validation,
    routing, persistence path) is the real production pipeline.
    """
    authenticate(client)
    application_id = create_application(client)
    add_document(
        storage_root,
        application_id,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        "scan.pdf",
        make_scanned_pdf_bytes(render_text_image()),
        "application/pdf",
    )
    run_validation(client, application_id)
    patch_ocr_engine(monkeypatch, fail=True)

    result = process_documents(client, application_id)

    assert result["total_processed"] == 0
    assert result["total_failed"] == 1
    assert result["items"][0]["outcome"] == "FAILED"
    assert get_ocr_results(client, application_id)["total"] == 0
    assert read_stored_rows(application_id) == []
