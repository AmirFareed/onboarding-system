"""Tests for the document completeness verification module.

Applications are created through the API; documents are inserted directly via
the ``DocumentRepository`` (bypassing the upload module's duplicate guard) so
duplicates and unexpected types can be constructed for verification. Only
database metadata is involved -- no files are written.
"""

import pytest
from sqlalchemy import func, select

from app.completeness.constants import (
    OPTIONAL_DOCUMENT_TYPES,
    REQUIRED_DOCUMENT_TYPES,
)
from app.database.connection import SessionLocal
from app.database.models.document import Document
from app.database.models.enums import (
    DocumentProcessingStatus,
    DocumentType,
)
from app.database.repositories.document_repository import DocumentRepository

API = "/api/v1"

REQUIRED = sorted(REQUIRED_DOCUMENT_TYPES, key=lambda item: item.value)
OPTIONAL = sorted(OPTIONAL_DOCUMENT_TYPES, key=lambda item: item.value)


def create_application(client, created_by: str = "tester") -> int:
    """Create an application via the API and return its id."""
    response = client.post(f"{API}/applications", json={"created_by": created_by})
    assert response.status_code == 201, response.text
    return response.json()["application"]["id"]


def insert_document(
    application_id: int,
    document_type: DocumentType,
    filename: str | None = None,
) -> None:
    """Insert a document row directly, without touching the storage backend.

    The copy slot defaults to the next free number for that (application,
    type) so duplicate scenarios can be constructed without colliding with the
    unique copy-slot index enforced by the database.
    """
    db = SessionLocal()
    try:
        existing = (
            db.execute(
                select(func.max(Document.copy_number)).where(
                    Document.application_id == application_id,
                    Document.document_type == document_type,
                )
            ).scalar()
            or 0
        )
        DocumentRepository(db).create(
            application_id=application_id,
            document_type=document_type,
            copy_number=int(existing) + 1,
            original_filename=filename or f"{document_type.value.lower()}.pdf",
            stored_file_path=(
                f"applications/APP-{application_id:06d}/test/"
                f"{document_type.value.lower()}.pdf"
            ),
            file_type="application/pdf",
            processing_status=DocumentProcessingStatus.UPLOADED,
        )
    finally:
        db.close()


def add_required_documents(application_id: int) -> None:
    """Insert exactly one copy of every required document type."""
    for document_type in REQUIRED:
        insert_document(application_id, document_type)


def verify(client, application_id: int, *, method: str = "get"):
    """Call a completeness endpoint and return the JSON report."""
    url = f"{API}/applications/{application_id}/completeness"
    if method == "post":
        url += "/verify"
    response = client.request(method, url)
    assert response.status_code == 200, response.text
    return response.json()


# --- Complete application ---------------------------------------------------


def test_complete_application(authenticated_client):
    application_id = create_application(authenticated_client)
    add_required_documents(application_id)

    report = verify(authenticated_client, application_id)

    assert report["application_id"] == application_id
    assert report["status"] == "COMPLETE"
    assert report["completion_percentage"] == 100.0
    assert report["missing_documents"] == []
    assert report["duplicate_documents"] == []
    assert report["unexpected_documents"] == []
    assert len(report["uploaded_documents"]) == 8
    assert len(report["required_documents"]) == 8
    assert all(item["is_present"] for item in report["required_documents"])
    assert all(item["copy_count"] == 1 for item in report["required_documents"])


# --- Missing documents ------------------------------------------------------


def test_missing_required_document(authenticated_client):
    application_id = create_application(authenticated_client)
    missing_type = REQUIRED[0]
    for document_type in REQUIRED:
        if document_type != missing_type:
            insert_document(application_id, document_type)

    report = verify(authenticated_client, application_id)

    assert report["status"] == "INCOMPLETE"
    assert report["missing_documents"] == [missing_type.value]
    assert report["completion_percentage"] == round(100.0 * 7 / 8, 2)
    assert report["duplicate_documents"] == []
    assert report["unexpected_documents"] == []


def test_multiple_missing_documents(authenticated_client):
    application_id = create_application(authenticated_client)
    for document_type in REQUIRED[2:]:
        insert_document(application_id, document_type)

    report = verify(authenticated_client, application_id)

    assert report["status"] == "INCOMPLETE"
    assert set(report["missing_documents"]) == {
        REQUIRED[0].value,
        REQUIRED[1].value,
    }
    assert report["completion_percentage"] == round(100.0 * 6 / 8, 2)


def test_empty_application(authenticated_client):
    application_id = create_application(authenticated_client)

    report = verify(authenticated_client, application_id)

    assert report["status"] == "INCOMPLETE"
    assert report["completion_percentage"] == 0.0
    assert report["uploaded_documents"] == []
    assert set(report["missing_documents"]) == {item.value for item in REQUIRED}


# --- Duplicates -------------------------------------------------------------


def test_duplicate_mandatory_document(authenticated_client):
    application_id = create_application(authenticated_client)
    add_required_documents(application_id)
    insert_document(application_id, DocumentType.TRIPARTITE_AGREEMENT, "scan2.pdf")

    report = verify(authenticated_client, application_id)

    assert report["status"] == "DUPLICATE_DOCUMENTS"
    assert report["duplicate_documents"] == [
        {
            "document_type": "TRIPARTITE_AGREEMENT",
            "copy_count": 2,
        }
    ]
    assert report["missing_documents"] == []


def test_duplicate_optional_document(authenticated_client):
    application_id = create_application(authenticated_client)
    add_required_documents(application_id)
    insert_document(application_id, DocumentType.OTHER_SUPPORTING_DOCUMENT)
    insert_document(application_id, DocumentType.OTHER_SUPPORTING_DOCUMENT, "other2.pdf")

    report = verify(authenticated_client, application_id)

    assert report["status"] == "DUPLICATE_DOCUMENTS"
    assert report["duplicate_documents"] == [
        {
            "document_type": "OTHER_SUPPORTING_DOCUMENT",
            "copy_count": 2,
        }
    ]


def test_duplicate_takes_precedence_over_incomplete(authenticated_client):
    application_id = create_application(authenticated_client)
    missing_type = REQUIRED[0]
    for document_type in REQUIRED:
        if document_type != missing_type:
            insert_document(application_id, document_type)
    insert_document(application_id, DocumentType.TRIPARTITE_AGREEMENT)
    insert_document(application_id, DocumentType.TRIPARTITE_AGREEMENT, "scan2.pdf")

    report = verify(authenticated_client, application_id)

    assert report["status"] == "DUPLICATE_DOCUMENTS"
    assert report["missing_documents"] == [missing_type.value]
    assert report["duplicate_documents"] == [
        {
            "document_type": "TRIPARTITE_AGREEMENT",
            "copy_count": 3,
        }
    ]


# --- Optional documents -----------------------------------------------------


def test_optional_documents_only(authenticated_client):
    application_id = create_application(authenticated_client)
    for document_type in OPTIONAL:
        insert_document(application_id, document_type)

    report = verify(authenticated_client, application_id)

    assert report["status"] == "INCOMPLETE"
    assert report["completion_percentage"] == 0.0
    assert set(report["missing_documents"]) == {item.value for item in REQUIRED}
    assert report["duplicate_documents"] == []
    assert report["unexpected_documents"] == []
    assert {item["document_type"] for item in report["uploaded_documents"]} == {
        item.value for item in OPTIONAL
    }


def test_optional_documents_with_complete_set(authenticated_client):
    application_id = create_application(authenticated_client)
    add_required_documents(application_id)
    insert_document(application_id, DocumentType.OTHER_SUPPORTING_DOCUMENT)

    report = verify(authenticated_client, application_id)

    assert report["status"] == "COMPLETE"
    assert len(report["uploaded_documents"]) == 9


# --- Unexpected documents ---------------------------------------------------


def test_unexpected_document_type(authenticated_client, monkeypatch):
    # CNIC_BACK, not CNIC_FRONT: CNIC_FRONT became a required type 2026-08-23
    # (see completeness/constants.py), so it no longer qualifies as "outside
    # the configured set". CNIC_BACK still genuinely does -- confirmed against
    # the real ALL_CONFIGURED_DOCUMENT_TYPES, not assumed.
    monkeypatch.setattr(
        "app.completeness.services.OPTIONAL_DOCUMENT_TYPES",
        frozenset({DocumentType.OTHER_SUPPORTING_DOCUMENT}),
    )
    monkeypatch.setattr(
        "app.completeness.services.ALL_CONFIGURED_DOCUMENT_TYPES",
        frozenset(REQUIRED_DOCUMENT_TYPES) | frozenset({DocumentType.OTHER_SUPPORTING_DOCUMENT}),
    )
    application_id = create_application(authenticated_client)
    add_required_documents(application_id)
    insert_document(application_id, DocumentType.CNIC_BACK)

    report = verify(authenticated_client, application_id)

    assert report["status"] == "INVALID_DOCUMENT_SET"
    assert report["unexpected_documents"] == [
        {
            "document_type": "CNIC_BACK",
            "copy_count": 1,
        }
    ]
    assert report["missing_documents"] == []


def test_invalid_document_set_takes_precedence(authenticated_client, monkeypatch):
    # CNIC_BACK, not CNIC_FRONT -- same reasoning as test_unexpected_document_type.
    monkeypatch.setattr(
        "app.completeness.services.OPTIONAL_DOCUMENT_TYPES",
        frozenset({DocumentType.OTHER_SUPPORTING_DOCUMENT}),
    )
    monkeypatch.setattr(
        "app.completeness.services.ALL_CONFIGURED_DOCUMENT_TYPES",
        frozenset(REQUIRED_DOCUMENT_TYPES) | frozenset({DocumentType.OTHER_SUPPORTING_DOCUMENT}),
    )
    application_id = create_application(authenticated_client)
    add_required_documents(application_id)
    insert_document(application_id, DocumentType.TRIPARTITE_AGREEMENT, "scan2.pdf")
    insert_document(application_id, DocumentType.CNIC_BACK)

    report = verify(authenticated_client, application_id)

    assert report["status"] == "INVALID_DOCUMENT_SET"
    assert report["duplicate_documents"] == [
        {
            "document_type": "TRIPARTITE_AGREEMENT",
            "copy_count": 2,
        }
    ]


# --- Application not found --------------------------------------------------


def test_application_not_found(authenticated_client):
    for method in ("get", "post"):
        response = authenticated_client.request(
            method,
            f"{API}/applications/999999/completeness"
            + ("/verify" if method == "post" else ""),
        )
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "Application not found"


# --- Endpoint behaviour -----------------------------------------------------


def test_get_and_verify_return_same_report(authenticated_client):
    application_id = create_application(authenticated_client)
    add_required_documents(application_id)

    get_report = verify(authenticated_client, application_id, method="get")
    post_report = verify(authenticated_client, application_id, method="post")

    for field in (
        "application_id",
        "status",
        "completion_percentage",
        "missing_documents",
        "duplicate_documents",
        "unexpected_documents",
        "uploaded_documents",
    ):
        assert get_report[field] == post_report[field], field


def test_uploaded_documents_expose_no_storage_path(authenticated_client):
    application_id = create_application(authenticated_client)
    insert_document(application_id, DocumentType.TRIPARTITE_AGREEMENT)

    report = verify(authenticated_client, application_id)

    assert "stored_file_path" not in report["uploaded_documents"][0]


# --- Configuration ----------------------------------------------------------


def test_invalid_configuration_raises(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "app.completeness.validators.REQUIRED_DOCUMENT_TYPES",
        frozenset(),
    )

    response = authenticated_client.get(f"{API}/applications/1/completeness")

    assert response.status_code == 500
    assert "must be configured" in response.json()["detail"]


def test_overlapping_configuration_raises(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "app.completeness.validators.REQUIRED_DOCUMENT_TYPES",
        frozenset(
            REQUIRED_DOCUMENT_TYPES | {DocumentType.OTHER_SUPPORTING_DOCUMENT}
        ),
    )

    response = authenticated_client.get(f"{API}/applications/1/completeness")

    assert response.status_code == 500
    assert "both required and optional" in response.json()["detail"]
