"""Tests for the document processing module.

Documents are written straight into the temporary storage root and inserted via
the ``DocumentRepository`` so tests control the exact bytes on disk. Every test
runs Phase 5 technical validation first (through the real API) so the processing
gate has PASS reports to read. OCR runs against a fake engine injected through
the service-level factory, keeping the tests fast and deterministic while the
routing, preprocessing, merging and persistence paths stay real.
"""

import time

import pymupdf

from app.document_processing.exceptions import OCRProcessingFailed
from app.document_processing.processors import OCRExtraction
from app.document_processing import services as processing_services
from app.document_processing.constants import (
    PADDLE_OCR_ENGINE,
    PYMUPDF_ENGINE,
    ProcessingMethod,
)
from app.database.models.enums import DocumentType
from tests.test_technical_validation_api import (
    add_document,
    create_application,
    encode_png,
    make_document_image,
    make_valid_pdf_bytes,
    run_validation,
)

API = "/api/v1"

OCR_URL = "/process-documents"
RESULTS_URL = "/ocr-results"


class FakeOCREngine:
    """Deterministic OCR engine standing in for PaddleOCR in tests."""

    def __init__(
        self,
        texts: list[str] | None = None,
        *,
        confidence: float | None = 0.95,
        sleep: float = 0.0,
        fail: bool = False,
    ) -> None:
        self._texts = texts or ["recognized line one", "recognized line two"]
        self.confidence = confidence
        self.sleep = sleep
        self.fail = fail
        self.calls = 0

    def extract(self, image) -> OCRExtraction:
        """Return the next canned text, optionally sleeping or failing."""
        self.calls += 1
        if self.fail:
            raise OCRProcessingFailed("simulated engine failure")
        if self.sleep:
            time.sleep(self.sleep)
        text = self._texts[min(self.calls - 1, len(self._texts) - 1)]
        return OCRExtraction(text=text, confidence=self.confidence)


def patch_ocr_engine(monkeypatch, **kwargs) -> FakeOCREngine:
    """Install a fake OCR engine as the service's engine factory."""
    engine = FakeOCREngine(**kwargs)
    monkeypatch.setattr(processing_services, "ocr_engine_factory", lambda: engine)
    return engine


def process_documents(client, application_id: int) -> dict:
    """Call the process-documents endpoint and return the JSON response."""
    response = client.post(f"{API}/applications/{application_id}{OCR_URL}")
    assert response.status_code == 200, response.text
    return response.json()


def get_ocr_results(client, application_id: int) -> dict:
    """Call the ocr-results endpoint and return the JSON response."""
    response = client.get(f"{API}/applications/{application_id}{RESULTS_URL}")
    assert response.status_code == 200, response.text
    return response.json()


def make_scanned_pdf_bytes(*images) -> bytes:
    """Build a scanned (image-only) PDF with one page per supplied image."""
    document = pymupdf.open()
    for image in images:
        page = document.new_page(width=400, height=566)
        page.insert_image(page.rect, stream=encode_png(image))
    content = document.tobytes()
    document.close()
    return content


# --- Digital PDF extraction --------------------------------------------------


def test_digital_pdf_extraction(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(pages=2, lines_per_page=10),
        "application/pdf",
    )
    run_validation(authenticated_client, application_id)
    engine = patch_ocr_engine(monkeypatch)

    result = process_documents(authenticated_client, application_id)

    assert result["total_processed"] == 1
    assert result["total_skipped"] == 0
    assert result["total_failed"] == 0
    item = result["items"][0]
    assert item["outcome"] == "PROCESSED"
    assert item["ocr_engine"] == PYMUPDF_ENGINE
    assert item["processing_method"] == ProcessingMethod.PYMUFPDF_TEXT_EXTRACTION.value
    assert item["overall_confidence"] is None
    assert item["page_count"] == 2
    assert item["character_count"] > 0
    assert item["character_count"] == len(item["raw_text"])
    assert "Page 1 line 1" in item["raw_text"]
    assert "Page 2 line 10" in item["raw_text"]
    assert engine.calls == 0, "digital PDFs must bypass OCR"


# --- Scanned PDF extraction --------------------------------------------------


def test_scanned_pdf_extraction(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.AUTHORITY_LETTER,
        "scan.pdf",
        make_scanned_pdf_bytes(make_document_image(lines=6)),
        "application/pdf",
    )
    run_validation(authenticated_client, application_id)
    engine = patch_ocr_engine(monkeypatch, texts=["scanned page text"])

    result = process_documents(authenticated_client, application_id)

    item = result["items"][0]
    assert item["outcome"] == "PROCESSED"
    assert item["ocr_engine"] == PADDLE_OCR_ENGINE
    assert item["processing_method"] == ProcessingMethod.PADDLE_OCR.value
    assert item["overall_confidence"] == 0.95
    assert item["page_count"] == 1
    assert "scanned page text" in item["raw_text"]
    assert engine.calls == 1


# --- Image extraction --------------------------------------------------------


def test_image_extraction(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "scan.png",
        encode_png(make_document_image(lines=10)),
        "image/png",
    )
    run_validation(authenticated_client, application_id)
    engine = patch_ocr_engine(monkeypatch, texts=["image page text"])

    result = process_documents(authenticated_client, application_id)

    item = result["items"][0]
    assert item["outcome"] == "PROCESSED"
    assert item["ocr_engine"] == PADDLE_OCR_ENGINE
    assert item["processing_method"] == ProcessingMethod.PADDLE_OCR.value
    assert item["page_count"] == 1
    assert "image page text" in item["raw_text"]
    assert engine.calls == 1


# --- Multi-page PDF ----------------------------------------------------------


def test_multi_page_scanned_pdf_preserves_page_order(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    first_page = make_document_image(lines=4)
    second_page = make_document_image(lines=4)
    add_document(
        storage_root,
        application_id,
        DocumentType.SCHEDULE_OF_CHARGES,
        "scan.pdf",
        make_scanned_pdf_bytes(first_page, second_page),
        "application/pdf",
    )
    run_validation(authenticated_client, application_id)
    patch_ocr_engine(monkeypatch, texts=["first page content", "second page content"])

    result = process_documents(authenticated_client, application_id)

    item = result["items"][0]
    assert item["outcome"] == "PROCESSED"
    assert item["page_count"] == 2
    assert "first page content" in item["raw_text"]
    assert "second page content" in item["raw_text"]
    assert item["raw_text"].index("first page content") < item["raw_text"].index(
        "second page content"
    )
    assert "--- Page 2 ---" in item["raw_text"]


def test_multi_page_digital_pdf(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.BILATERAL_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(pages=3, lines_per_page=5),
        "application/pdf",
    )
    run_validation(authenticated_client, application_id)
    engine = patch_ocr_engine(monkeypatch)

    item = process_documents(authenticated_client, application_id)["items"][0]

    assert item["page_count"] == 3
    assert item["raw_text"].index("Page 1 line") < item["raw_text"].index("Page 3 line")
    assert engine.calls == 0


# --- Empty extraction --------------------------------------------------------


def test_ocr_empty_extraction_fails_document(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        "scan.pdf",
        make_scanned_pdf_bytes(make_document_image(lines=6)),
        "application/pdf",
    )
    run_validation(authenticated_client, application_id)
    patch_ocr_engine(monkeypatch, texts=[""])

    result = process_documents(authenticated_client, application_id)

    assert result["total_processed"] == 0
    assert result["total_failed"] == 1
    item = result["items"][0]
    assert item["outcome"] == "FAILED"
    assert "no text" in item["message"]


def test_blank_pdf_is_skipped(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    blank = pymupdf.open()
    blank.new_page(width=400, height=566)
    content = blank.tobytes()
    blank.close()
    add_document(
        storage_root,
        application_id,
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        "blank.pdf",
        content,
        "application/pdf",
    )
    report = run_validation(authenticated_client, application_id)
    assert report["items"][0]["validation_status"] == "FAIL"
    engine = patch_ocr_engine(monkeypatch)

    result = process_documents(authenticated_client, application_id)

    assert result["total_processed"] == 0
    assert result["total_skipped"] == 1
    assert result["items"][0]["outcome"] == "SKIPPED"
    assert engine.calls == 0


# --- OCR failure -------------------------------------------------------------


def test_ocr_failure_is_captured_per_document(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "scan.png",
        encode_png(make_document_image(lines=10)),
        "image/png",
    )
    run_validation(authenticated_client, application_id)
    patch_ocr_engine(monkeypatch, fail=True)

    result = process_documents(authenticated_client, application_id)

    assert result["total_processed"] == 0
    assert result["total_failed"] == 1
    item = result["items"][0]
    assert item["outcome"] == "FAILED"
    assert item["ocr_engine"] is None
    assert item["message"] == "simulated engine failure"


# --- Technical validation gate ------------------------------------------------


def test_technically_invalid_document_is_skipped(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    import cv2

    blurred = cv2.GaussianBlur(make_document_image(lines=10), (15, 15), 0)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "blurry.png",
        encode_png(blurred),
        "image/png",
    )
    report = run_validation(authenticated_client, application_id)
    assert report["items"][0]["validation_status"] == "FAIL"
    engine = patch_ocr_engine(monkeypatch)

    result = process_documents(authenticated_client, application_id)

    assert result["total_processed"] == 0
    assert result["total_skipped"] == 1
    item = result["items"][0]
    assert item["outcome"] == "SKIPPED"
    assert "technical validation" in item["message"]
    assert engine.calls == 0


def test_processing_requires_technical_validation(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(),
        "application/pdf",
    )
    patch_ocr_engine(monkeypatch)

    response = authenticated_client.post(f"{API}/applications/{application_id}{OCR_URL}")

    assert response.status_code == 400
    assert "technical validation" in response.json()["detail"].lower()


# --- Mixed application -------------------------------------------------------


def test_mixed_application(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(pages=1, lines_per_page=10),
        "application/pdf",
    )
    add_document(
        storage_root,
        application_id,
        DocumentType.AUTHORITY_LETTER,
        "scan.pdf",
        make_scanned_pdf_bytes(make_document_image(lines=6)),
        "application/pdf",
    )
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "scan.png",
        encode_png(make_document_image(lines=10)),
        "image/png",
    )
    run_validation(authenticated_client, application_id)
    engine = patch_ocr_engine(monkeypatch, texts=["ocr text"])

    result = process_documents(authenticated_client, application_id)

    assert result["total_processed"] == 3
    assert result["total_skipped"] == 0
    assert result["total_failed"] == 0
    engines = {item["ocr_engine"] for item in result["items"]}
    assert engines == {PYMUPDF_ENGINE, PADDLE_OCR_ENGINE}
    assert engine.calls == 2  # scanned PDF page + image


# --- Application-level behaviour ---------------------------------------------


def test_application_not_found(authenticated_client):
    assert (
        authenticated_client.post(f"{API}/applications/999999{OCR_URL}").status_code == 404
    )
    assert authenticated_client.get(f"{API}/applications/999999{RESULTS_URL}").status_code == 404


def test_empty_application_processes_nothing(authenticated_client, monkeypatch):
    application_id = create_application(authenticated_client)
    patch_ocr_engine(monkeypatch)

    result = process_documents(authenticated_client, application_id)

    assert result["total_processed"] == 0
    assert result["total_skipped"] == 0
    assert result["total_failed"] == 0
    assert result["items"] == []


# --- Stored results ----------------------------------------------------------


def test_get_ocr_results_returns_stored_extractions(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(pages=2, lines_per_page=5),
        "application/pdf",
    )
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "scan.png",
        encode_png(make_document_image(lines=10)),
        "image/png",
    )
    run_validation(authenticated_client, application_id)
    patch_ocr_engine(monkeypatch, texts=["ocr stored text"])

    assert get_ocr_results(authenticated_client, application_id)["total"] == 0

    processed = process_documents(authenticated_client, application_id)
    stored = get_ocr_results(authenticated_client, application_id)

    assert stored["total"] == 2
    stored_by_document = {item["document_id"]: item for item in stored["items"]}
    for item in processed["items"]:
        stored_item = stored_by_document[item["document_id"]]
        assert stored_item["raw_ocr_text"] == item["raw_text"]
        assert stored_item["ocr_engine"] == item["ocr_engine"]
        assert stored_item["processing_method"] == item["processing_method"]
        assert stored_item["page_count"] == item["page_count"]
        assert stored_item["character_count"] == item["character_count"]
        assert stored_item["overall_confidence"] == item["overall_confidence"]
        assert stored_item["processed_at"] is not None
    assert stored["items"][0]["file_name"] == "agreement.pdf"
    assert stored["items"][1]["file_name"] == "scan.png"


def test_reprocessing_updates_the_stored_result(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "scan.png",
        encode_png(make_document_image(lines=10)),
        "image/png",
    )
    run_validation(authenticated_client, application_id)
    patch_ocr_engine(monkeypatch, texts=["first run text"])

    process_documents(authenticated_client, application_id)
    first = get_ocr_results(authenticated_client, application_id)
    assert first["total"] == 1
    assert first["items"][0]["raw_ocr_text"] == "first run text"

    patch_ocr_engine(monkeypatch, texts=["second run text"])
    process_documents(authenticated_client, application_id)
    second = get_ocr_results(authenticated_client, application_id)

    assert second["total"] == 1
    assert second["items"][0]["raw_ocr_text"] == "second run text"
