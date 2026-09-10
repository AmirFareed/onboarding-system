"""Tests for the technical file validation module.

Applications are created through the API; documents are written straight into
the (temporary) storage root and inserted via the ``DocumentRepository`` so the
tests control the exact bytes on disk -- including corrupted, password-protected
and missing files that the upload module would never store. Real PDFs are built
with PyMuPDF and real images with OpenCV so the analysis code paths are
exercised end to end.
"""

from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pymupdf

from app.database.connection import SessionLocal
from app.database.models.enums import DocumentProcessingStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.technical_validation.constants import BLUR_THRESHOLD, MIN_IMAGE_HEIGHT, MIN_IMAGE_WIDTH
from app.upload.constants import DOCUMENT_TYPE_SLUGS

API = "/api/v1"


def create_application(client, created_by: str = "tester") -> int:
    """Create an application via the API and return its id."""
    response = client.post(f"{API}/applications", json={"created_by": created_by})
    assert response.status_code == 201, response.text
    return response.json()["application"]["id"]


def create_application_direct(created_by: str = "tester") -> int:
    """Create an application straight through the repository, bypassing HTTP.

    Every role-client fixture (``it_client``, ``reviewer_client``, ...) wraps
    the same underlying ``client``/cookie jar, so requesting a second one in
    the same test to create setup data silently overwrites the first login's
    session -- whichever fixture resolves last decides who every subsequent
    request on *both* names is actually authenticated as. Tests that need an
    application to exist before exercising IT/Reviewer-only read behavior
    should use this helper for setup instead of a second client fixture, the
    same way this module already writes documents straight into storage/the
    ``DocumentRepository`` rather than through the upload endpoints.
    """
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by=created_by)
        db.commit()
        return application.id
    finally:
        db.close()


def make_valid_pdf_bytes(pages: int = 2, lines_per_page: int = 10) -> bytes:
    """Build a real, renderable multi-page PDF with PyMuPDF."""
    document = pymupdf.open()
    for page_number in range(pages):
        page = document.new_page(width=595, height=842)
        y = 72
        for line in range(lines_per_page):
            page.insert_text(
                (72, y),
                f"Page {page_number + 1} line {line + 1}: sample contract text.",
                fontsize=14,
            )
            y += 25
    content = document.tobytes()
    document.close()
    return content


def make_password_protected_pdf_bytes() -> bytes:
    """Build a PDF encrypted with a user password via PyMuPDF."""
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 100), "Confidential", fontsize=24)
    content = document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret",
        owner_pw="owner",
    )
    document.close()
    return content


def make_document_image(
    lines: int = 10,
    angle: float = 0.0,
    size: tuple[int, int] = (1600, 2200),
) -> np.ndarray:
    """Build a synthetic 'document' image: white page with horizontal text lines.

    Sharp horizontal lines give a deterministic blur score and rotation angle,
    unlike noise which produces unreliable Hough results.
    """
    width, height = size
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    step = height // (lines + 1)
    for line in range(1, lines + 1):
        cv2.line(image, (0, line * step), (width, line * step), (0, 0, 0), 3)
    if angle:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        image = cv2.warpAffine(image, matrix, (width, height), borderValue=(255, 255, 255))
    return image


def encode_png(image: np.ndarray) -> bytes:
    """Encode an image as PNG bytes."""
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


def encode_tiff(image: np.ndarray) -> bytes:
    """Encode an image as TIFF bytes (an unsupported technical format)."""
    ok, buffer = cv2.imencode(".tiff", image)
    assert ok
    return buffer.tobytes()


def add_document(
    storage_root: Path,
    application_id: int,
    document_type: DocumentType,
    filename: str,
    content: bytes,
    mime_type: str,
    *,
    write_file: bool = True,
) -> int:
    """Write a file into the storage root and insert its document metadata.

    Mirrors the upload storage layout so the technical validation service can
    resolve the stored path. When ``write_file`` is False the file is not
    written, producing a missing-file document.

    Returns:
        The id of the inserted document.
    """
    slug = DOCUMENT_TYPE_SLUGS[document_type]
    folder = f"applications/APP-{application_id:06d}/{slug}"
    directory = Path(storage_root) / folder
    directory.mkdir(parents=True, exist_ok=True)
    storage_name = f"{uuid4().hex}{Path(filename).suffix}"
    if write_file:
        (directory / storage_name).write_bytes(content)

    db = SessionLocal()
    try:
        document = DocumentRepository(db).create(
            application_id=application_id,
            document_type=document_type,
            original_filename=filename,
            stored_file_path=f"{folder}/{storage_name}",
            file_type=mime_type,
            processing_status=DocumentProcessingStatus.UPLOADED,
        )
        return document.id
    finally:
        db.close()


def run_validation(client, application_id: int, *, method: str = "post") -> dict:
    """Call a technical validation endpoint and return the JSON response."""
    url = f"{API}/applications/{application_id}/technical-validation"
    if method == "post":
        url += "/validate"
    response = client.request(method, url)
    assert response.status_code == 200, response.text
    return response.json()


# --- Valid documents ---------------------------------------------------------


def test_valid_pdf(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(),
        "application/pdf",
    )

    report = run_validation(authenticated_client, application_id)

    assert report["total"] == 1
    item = report["items"][0]
    assert item["validation_status"] == "PASS"
    assert item["file_type"] == "PDF"
    assert item["file_accessible"] is True
    assert item["file_type_valid"] is True
    assert item["pdf_valid"] is True
    assert item["image_valid"] is None
    assert item["readability_status"] == "READABLE"
    assert item["rotation_status"] == "NOT_ROTATED"
    assert item["blur_score"] is not None
    assert item["rotation_angle"] is not None
    assert item["failed_checks"] == []
    assert item["warnings"] == []
    assert "suitable for processing" in item["recommendations"][0]


def test_valid_image(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "scan.png",
        encode_png(make_document_image()),
        "image/png",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "PASS"
    assert item["file_type"] == "PNG"
    assert item["image_valid"] is True
    assert item["pdf_valid"] is None
    assert item["readability_status"] == "READABLE"
    assert item["rotation_status"] == "NOT_ROTATED"
    assert item["blur_score"] >= BLUR_THRESHOLD
    assert item["failed_checks"] == []


def test_unsupported_format(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        "scan.tiff",
        encode_tiff(make_document_image(lines=3)),
        "image/tiff",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert item["file_type"] == "TIFF"
    assert item["file_type_valid"] is False
    assert "File type is supported" in item["failed_checks"]
    assert item["readability_status"] == "UNREADABLE"
    assert any("PDF, JPEG or PNG" in rec for rec in item["recommendations"])


# --- File accessibility ------------------------------------------------------


def test_empty_file(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.AUTHORITY_LETTER,
        "empty.pdf",
        b"",
        "application/pdf",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert item["file_accessible"] is False
    assert "File is not empty" in item["failed_checks"]
    assert "PDF can be opened" in item["failed_checks"]
    assert item["readability_status"] == "UNREADABLE"


def test_missing_file(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.FORMAL_REQUEST_LETTER,
        "missing.pdf",
        b"",
        "application/pdf",
        write_file=False,
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert item["file_accessible"] is False
    assert "File exists" in item["failed_checks"]
    assert item["readability_status"] == "UNREADABLE"


# --- Corrupted / protected PDFs ---------------------------------------------


def test_corrupted_pdf(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.SCHEDULE_OF_CHARGES,
        "corrupt.pdf",
        b"this is not a pdf at all" * 20,
        "application/pdf",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert item["pdf_valid"] is False
    assert "PDF can be opened" in item["failed_checks"]
    assert item["readability_status"] == "UNREADABLE"


def test_password_protected_pdf(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        "protected.pdf",
        make_password_protected_pdf_bytes(),
        "application/pdf",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert item["pdf_valid"] is False
    assert "PDF is not password protected" in item["failed_checks"]
    assert item["readability_status"] == "UNREADABLE"
    assert any("without password protection" in rec for rec in item["recommendations"])


# --- Blur / rotation ---------------------------------------------------------


def test_blurry_image(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    sharp = make_document_image(lines=10)
    blurred = cv2.GaussianBlur(sharp, (15, 15), 0)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "blurry.png",
        encode_png(blurred),
        "image/png",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert item["blur_score"] < BLUR_THRESHOLD
    assert "Image is not blurry" in item["failed_checks"]
    assert item["readability_status"] == "UNREADABLE"


def test_low_resolution_image(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    small = make_document_image(lines=4, size=(400, 500))
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "small.png",
        encode_png(small),
        "image/png",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert item["image_valid"] is False
    assert "Image resolution meets minimum" in item["failed_checks"]
    assert item["blur_score"] >= BLUR_THRESHOLD
    assert any(str(MIN_IMAGE_WIDTH) in rec for rec in item["recommendations"])


def test_rotated_image(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    rotated = make_document_image(lines=20, angle=10.0)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "rotated.png",
        encode_png(rotated),
        "image/png",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "WARNING"
    assert item["rotation_status"] == "ROTATED"
    assert abs(item["rotation_angle"]) >= 3.0
    assert "Document is not rotated" in item["warnings"]
    assert item["readability_status"] == "PARTIALLY_READABLE"


# --- Blank pages -------------------------------------------------------------


def test_blank_image(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    blank = np.full((1600, 2200, 3), 255, dtype=np.uint8)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "blank.png",
        encode_png(blank),
        "image/png",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert "Page is not blank" in item["failed_checks"]
    assert item["readability_status"] == "UNREADABLE"
    assert any("contains content" in rec for rec in item["recommendations"])


def test_blank_pdf_first_page(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    document = pymupdf.open()
    document.new_page(width=595, height=842)
    content = document.tobytes()
    document.close()

    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "blank.pdf",
        content,
        "application/pdf",
    )

    item = run_validation(authenticated_client, application_id)["items"][0]

    assert item["validation_status"] == "FAIL"
    assert "Page is not blank" in item["failed_checks"]


# --- Application-level behaviour --------------------------------------------


def test_multiple_documents_in_one_application(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
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
        DocumentType.ONE_LINK_LETTER,
        "scan.png",
        encode_png(make_document_image()),
        "image/png",
    )
    blurred = cv2.GaussianBlur(make_document_image(), (15, 15), 0)
    add_document(
        storage_root,
        application_id,
        DocumentType.AUTHORITY_LETTER,
        "blurry.png",
        encode_png(blurred),
        "image/png",
    )

    report = run_validation(authenticated_client, application_id)

    assert report["application_id"] == application_id
    assert report["total"] == 3
    assert len(report["items"]) == 3
    statuses = {item["validation_status"] for item in report["items"]}
    assert "PASS" in statuses
    assert "FAIL" in statuses


def test_empty_application(authenticated_client):
    application_id = create_application(authenticated_client)

    report = run_validation(authenticated_client, application_id)

    assert report["total"] == 0
    assert report["items"] == []


def test_application_not_found(authenticated_client):
    assert authenticated_client.get(f"{API}/applications/999999/technical-validation").status_code == 404
    assert (
        authenticated_client.post(f"{API}/applications/999999/technical-validation/validate").status_code
        == 404
    )


# --- Storage and reconstruction ---------------------------------------------


def test_get_returns_stored_reports(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
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
        DocumentType.ONE_LINK_LETTER,
        "scan.png",
        encode_png(make_document_image()),
        "image/png",
    )

    assert run_validation(authenticated_client, application_id, method="get")["total"] == 0

    posted = run_validation(authenticated_client, application_id)
    stored = run_validation(authenticated_client, application_id, method="get")

    assert stored["total"] == 2
    posted_by_document_id = {item["document_id"]: item for item in posted["items"]}
    stored_by_document_id = {item["document_id"]: item for item in stored["items"]}
    assert set(posted_by_document_id) == set(stored_by_document_id)
    for document_id, item in stored_by_document_id.items():
        assert item["validation_status"] == posted_by_document_id[document_id]["validation_status"]
        assert item["file_type"] == posted_by_document_id[document_id]["file_type"]
        assert item["blur_score"] == posted_by_document_id[document_id]["blur_score"]
        assert item["rotation_angle"] == posted_by_document_id[document_id]["rotation_angle"]


def test_report_never_exposes_storage_path(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.TRIPARTITE_AGREEMENT,
        "agreement.pdf",
        make_valid_pdf_bytes(),
        "application/pdf",
    )

    report = run_validation(authenticated_client, application_id)
    serialized = repr(report)

    assert "stored_file_path" not in serialized
    assert "applications/APP-" not in serialized
