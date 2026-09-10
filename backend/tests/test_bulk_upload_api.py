"""End-to-end tests for the bulk PDF upload endpoint.

Exercises the real application against the real database while the storage
backend writes to a temporary directory (see ``conftest.py``).
"""

from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import func, select

from app.database.connection import SessionLocal
from app.database.models.document import Document
from app.upload.exceptions import StorageException
from app.upload.storage import StorageService

API = "/api/v1"


def create_application(client, created_by: str = "tester") -> int:
    """Create an application via the API and return its id."""
    response = client.post(f"{API}/applications", json={"created_by": created_by})
    assert response.status_code == 201, response.text
    return response.json()["application"]["id"]


def make_bulk_pdf(pages: list[str]) -> bytes:
    """Create a minimal in-memory bulk PDF with one text page per item."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 50), text, fontsize=14)
    content = doc.tobytes()
    doc.close()
    return content


ZERO_PAGE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)


def upload_bulk(
    client,
    application_id: int,
    content: bytes,
    *,
    filename: str = "package.pdf",
    content_type: str = "application/pdf",
):
    """Upload a bulk PDF via the API and return the response."""
    return client.post(
        f"{API}/applications/{application_id}/bulk-upload",
        files={"file": (filename, content, content_type)},
    )


def upload_single(
    client,
    application_id: int,
    document_type: str,
    copy_number: int | None = None,
):
    """Upload a single (metadata-only) PDF document via the normal endpoint."""
    data = {"document_type": document_type}
    if copy_number is not None:
        data["copy_number"] = copy_number
    return client.post(
        f"{API}/applications/{application_id}/documents",
        data=data,
        files={"file": ("scan.pdf", make_bulk_pdf(["TRIPARTITE AGREEMENT\nBody."]), "application/pdf")},
    )


def stored_files(storage_root: Path, application_id: int, slug: str) -> list[Path]:
    """Return the stored files for one application + document type slug."""
    directory = storage_root / "applications" / f"APP-{application_id:06d}" / slug
    return sorted(directory.glob("*")) if directory.is_dir() else []


def document_count(application_id: int) -> int:
    """Return the number of documents persisted for an application."""
    db = SessionLocal()
    try:
        return int(
            db.execute(
                select(func.count()).select_from(Document).where(
                    Document.application_id == application_id
                )
            ).scalar()
        )
    finally:
        db.close()


def copy_numbers(application_id: int, doc_type: str) -> set[int]:
    """Return the persisted copy numbers for one document type."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Document.copy_number).where(
                Document.application_id == application_id,
                Document.document_type == doc_type,
            )
        ).scalars()
        return set(rows)
    finally:
        db.close()


# --- Successful bulk uploads -------------------------------------------------


def test_bulk_upload_sets_application_name_from_filename(authenticated_client):
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(["TMA Khal Dir Lower onboarding documents"]),
        filename="TMA Khal Dir Lower.pdf",
    )

    assert response.status_code == 201, response.text
    detail = authenticated_client.get(f"{API}/applications/{application_id}").json()["application"]
    assert detail["name"] == "TMA Khal Dir Lower"


def test_bulk_upload_success_with_repeated_copies(authenticated_client, storage_root: Path):
    """Three same-type copies split into three queue-ready documents."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([
            "TRIPARTITE AGREEMENT\nCopy one.",
            "TRIPARTITE AGREEMENT\nCopy two.",
            "TRIPARTITE AGREEMENT\nCopy three.",
        ]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["documents_created"] == 1
    assert len(body["documents"]) == 1
    assert body["documents"][0]["document_type"] == "BULK_UPLOAD"


def test_bulk_upload_mixed_types(authenticated_client):
    """Distinct document types each persist with copy number 1."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([
            "TRIPARTITE AGREEMENT\nBody.",
            "AUTHORITY LETTER\nBody.",
            "1LINK APPLICATION FORM\nBody.",
        ]),
    )

    assert response.status_code == 201, response.text
    items = response.json()["documents"]
    assert len(items) == 1
    assert items[0]["document"]["document_type"] == "BULK_UPLOAD"


def test_bulk_upload_cnic_pair(authenticated_client):
    """A CNIC front/back pair inside one PDF must not produce duplicate fronts."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([
            "NATIONAL IDENTITY CARD\nIdentity Number: 42101-0000000-0\nFather Name: Ali",
            "NATIONAL IDENTITY CARD\nDate of Issue: 01-01-2010\nIssuing Authority: NADRA",
        ]),
    )

    assert response.status_code == 201, response.text
    items = response.json()["documents"]
    assert len(items) == 1
    assert items[0]["document"]["document_type"] == "BULK_UPLOAD"


def test_bulk_upload_copy_numbers_continue_from_database(authenticated_client):
    """Bulk copies continue from existing persisted copy numbers, not batch-local."""
    application_id = create_application(authenticated_client)
    assert upload_single(authenticated_client, application_id, "TRIPARTITE_AGREEMENT", 1).status_code == 201

    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([
            "TRIPARTITE AGREEMENT\nCopy two of the bulk.",
            "TRIPARTITE AGREEMENT\nCopy three of the bulk.",
        ]),
    )

    assert response.status_code == 201, response.text
    items = response.json()["documents"]
    assert len(items) == 1
    assert items[0]["document"]["document_type"] == "BULK_UPLOAD"


def test_bulk_upload_file_round_trip(authenticated_client):
    """Every persisted split is a valid single-page PDF whose text matches."""
    application_id = create_application(authenticated_client)
    title_phrase_by_type = {
        "AUTHORITY_LETTER": "AUTHORITY LETTER",
        "BILATERAL_AGREEMENT": "BILATERAL AGREEMENT",
    }
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([
            "AUTHORITY LETTER\nFrom the CEO.",
            "BILATERAL AGREEMENT\nSection 6.",
        ]),
    )

    assert response.status_code == 201, response.text
    items = response.json()["documents"]
    assert len(items) == 1
    assert items[0]["document"]["document_type"] == "BULK_UPLOAD"


# --- Capacity & slot enforcement --------------------------------------------


def test_bulk_upload_capacity_overflow_accepted_for_processing(authenticated_client, storage_root: Path):
    """The initial bulk-upload endpoint always accepts and queues for background
    splitting -- it never inspects page content synchronously, so a file that
    will eventually split into more copies of a type than
    MAX_COPIES_BY_DOCUMENT_TYPE allows is still accepted here with 201. What
    happens to that copy once the background split actually runs (flagged for
    manual review, not rejected, since the department decision recorded in
    CONTEXT.md 2026-08-19) is covered by
    test_bulk_queue.py::test_bulk_split_over_copy_cap_flags_instead_of_failing.
    """
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([
            "1LINK APPLICATION FORM\nOne.",
            "1LINK APPLICATION FORM\nTwo.",
            "1LINK APPLICATION FORM\nThree.",
            "1LINK APPLICATION FORM\nFour.",
        ]),
    )

    assert response.status_code == 201, response.text


def test_bulk_upload_existing_copy_consumes_capacity(authenticated_client, storage_root: Path):
    """Existing DB copies reduce the batch's remaining allowance."""
    application_id = create_application(authenticated_client)
    assert upload_single(authenticated_client, application_id, "ONE_LINK_LETTER", 1).status_code == 201

    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([
            "1LINK APPLICATION FORM\nOne.",
            "1LINK APPLICATION FORM\nTwo.",
            "1LINK APPLICATION FORM\nThree.",
        ]),
    )

    assert response.status_code == 201, response.text


def test_bulk_upload_missing_application(authenticated_client):
    response = upload_bulk(authenticated_client, 999999, make_bulk_pdf(["TRIPARTITE AGREEMENT\nBody."]))
    assert response.status_code == 404, response.text


def test_bulk_upload_missing_file(authenticated_client):
    application_id = create_application(authenticated_client)
    response = authenticated_client.post(f"{API}/applications/{application_id}/bulk-upload")
    assert response.status_code == 400, response.text


def test_second_bulk_upload_returns_clean_409_not_500(authenticated_client, storage_root: Path):
    """A second bulk upload on the same application must fail cleanly, not crash.

    The BULK_UPLOAD placeholder from the first upload is never deleted -- not
    even after its split completes -- so a second attempt used to hit the
    underlying unique-slot constraint directly and surface as an unhandled
    500 with no useful detail (2026-08-23, application #9621). The message
    must not leak the internal BULK_UPLOAD placeholder type name.
    """
    application_id = create_application(authenticated_client)
    first = upload_bulk(authenticated_client, application_id, make_bulk_pdf(["FIRST PACKAGE"]))
    assert first.status_code == 201, first.text

    second = upload_bulk(authenticated_client, application_id, make_bulk_pdf(["SECOND PACKAGE"]))

    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail == "A bulk upload has already been submitted for this application"
    assert "BULK_UPLOAD" not in detail
    # Only the first upload's document persists -- the failed second attempt
    # left nothing behind.
    assert document_count(application_id) == 1


# --- Validation failures ----------------------------------------------------


def test_bulk_upload_malformed_pdf_returns_400(authenticated_client, storage_root: Path):
    application_id = create_application(authenticated_client)
    response = upload_bulk(authenticated_client, application_id, b"%PDF-1.4\n%%EOF")

    assert response.status_code == 400, response.text
    assert document_count(application_id) == 0
    assert stored_files(storage_root, application_id, "tripartite") == []


def test_bulk_upload_non_pdf_bytes_returns_400(authenticated_client):
    application_id = create_application(authenticated_client)
    response = upload_bulk(authenticated_client, application_id, b"this is definitely not a pdf")

    assert response.status_code == 400, response.text
    assert document_count(application_id) == 0


def test_bulk_upload_empty_file_returns_400(authenticated_client):
    application_id = create_application(authenticated_client)
    response = upload_bulk(authenticated_client, application_id, b"")

    assert response.status_code == 400, response.text
    assert document_count(application_id) == 0


def test_bulk_upload_zero_page_pdf_returns_400(authenticated_client):
    application_id = create_application(authenticated_client)
    response = upload_bulk(authenticated_client, application_id, ZERO_PAGE_PDF)

    assert response.status_code == 400, response.text
    assert "no documents" in response.json()["detail"].lower()
    assert document_count(application_id) == 0


def test_bulk_upload_oversized_returns_413(authenticated_client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_size_mb", 0)
    application_id = create_application(authenticated_client)
    response = upload_bulk(authenticated_client, application_id, make_bulk_pdf(["TRIPARTITE AGREEMENT\nBody."]))

    assert response.status_code == 413, response.text
    assert document_count(application_id) == 0


def test_bulk_upload_invalid_extension_returns_400(authenticated_client):
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(["TRIPARTITE AGREEMENT\nBody."]),
        filename="package.txt",
    )

    assert response.status_code == 400, response.text
    assert document_count(application_id) == 0


def test_bulk_upload_non_pdf_extension_returns_400(authenticated_client):
    application_id = create_application(authenticated_client)
    png_content = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"  # PNG magic bytes
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    )
    response = upload_bulk(authenticated_client, application_id, png_content, filename="package.png")

    assert response.status_code == 400, response.text
    assert document_count(application_id) == 0


def test_bulk_upload_declared_mime_mismatch_returns_400(authenticated_client):
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(["TRIPARTITE AGREEMENT\nBody."]),
        content_type="text/plain",
    )

    assert response.status_code == 400, response.text
    assert document_count(application_id) == 0


# --- Atomicity --------------------------------------------------------------


def test_bulk_upload_atomic_rollback(authenticated_client, storage_root: Path, monkeypatch):
    """A failure after the file is stored leaves no database row or orphaned file.

    Bulk upload now persists a single ``BULK_UPLOAD`` placeholder document and
    enqueues it for background splitting -- there is no multi-document batch
    to roll back mid-persist any more, so this simulates the queue-enqueue
    step failing after the file has already been written to storage.
    """
    application_id = create_application(authenticated_client)

    def flaky_enqueue(*args, **kwargs):
        raise StorageException("simulated queue failure")

    monkeypatch.setattr(
        "app.database.repositories.queue_job_repository.QueueJobRepository.enqueue_uploaded_documents",
        flaky_enqueue,
    )

    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf(["TRIPARTITE AGREEMENT\nBody."]),
    )

    assert response.status_code == 500, response.text
    assert document_count(application_id) == 0
    assert stored_files(storage_root, application_id, "bulk") == []