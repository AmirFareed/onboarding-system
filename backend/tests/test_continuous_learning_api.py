"""Tests for the continuous learning API.

End-to-end tests build curated datasets through the real pipeline (a final
review and a low-confidence scan) and through direct repository inserts for
precise aggregation, filtering, hashing and version checks. The tests cover
dataset generation, statistics, metadata, deterministic hashing, exclusion of
invalid and duplicate records, JSON/CSV exports, version consistency, 404 cases
and empty datasets.
"""

import csv
import hashlib
import io
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.continuous_learning.constants import CSV_COLUMNS, HASH_ALGORITHM
from app.database.connection import SessionLocal
from app.database.models.enums import DocumentType
from app.database.models.feedback_dataset import FeedbackEntry
from app.database.repositories.document_repository import DocumentRepository
from tests.test_document_analysis_api import add_digital_pdf
from tests.test_feedback_api import final_correct_review, insert_feedback
from tests.test_reports_api import build_single_statement_application
from tests.test_technical_validation_api import create_application

API = "/api/v1"

DATASET_URL = "/continuous-learning/dataset"
STATISTICS_URL = "/continuous-learning/statistics"
EXPORT_JSON_URL = "/continuous-learning/export/json"
EXPORT_CSV_URL = "/continuous-learning/export/csv"
VERSION_URL = "/continuous-learning/version"


@pytest.fixture(autouse=True)
def isolated_feedback():
    """Guarantee an empty feedback dataset around every test.

    The conftest database wipe deletes applications, which only ``SET NULL``s
    the application reference of feedback rows; this fixture removes the rows
    themselves so global feedback state is deterministic per test.
    """
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM feedback_dataset"))
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM feedback_dataset"))
        db.commit()
    finally:
        db.close()


def insert_raw(rows: list[dict]) -> list[int]:
    """Insert feedback rows directly, allowing explicit timestamps and nulls."""
    db = SessionLocal()
    try:
        ids = []
        for row in rows:
            entry = FeedbackEntry(
                recorded_at=row.pop("recorded_at", datetime.now(timezone.utc)),
                **row,
            )
            db.add(entry)
            db.flush()
            ids.append(entry.id)
        db.commit()
        return ids
    finally:
        db.close()


def build_curated_application(client, storage_root) -> int:
    """Build an application with two valid curated samples from a final review."""
    application_id = build_single_statement_application(client, storage_root)
    assert final_correct_review(client, application_id).status_code == 200
    return application_id


def five_valid_samples(client, storage_root) -> tuple[int, dict]:
    """Insert five valid samples over two documents; return the document map."""
    application_id = create_application(client)
    add_digital_pdf(
        storage_root,
        application_id,
        "statement",
        document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        filename="a.pdf",
    )
    add_digital_pdf(
        storage_root,
        application_id,
        "statement",
        document_type=DocumentType.ONE_LINK_LETTER,
        filename="b.pdf",
    )
    documents = DocumentRepository(SessionLocal()).get_by_application(application_id)
    doc_a = next(
        d.id
        for d in documents
        if d.document_type is DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
    )
    doc_b = next(
        d.id
        for d in documents
        if d.document_type is DocumentType.ONE_LINK_LETTER
    )
    insert_feedback(
        [
            {
                "document_id": doc_a,
                "field_name": "account_number",
                "ocr_value": "1234567890",
                "human_value": "1111111111",
                "confidence_score": 0.9,
                "confidence_source": "regex",
                "reviewer": "alice",
                "decision": "CORRECT",
                "origin": "FINAL_HUMAN_REVIEW",
            },
            {
                "document_id": doc_a,
                "field_name": "account_number",
                "ocr_value": "1234567890",
                "human_value": "2222222222",
                "confidence_score": 0.8,
                "reviewer": "alice",
                "decision": "CORRECT",
                "origin": "FINAL_HUMAN_REVIEW",
            },
            {
                "document_id": doc_a,
                "field_name": "account_number",
                "ocr_value": "1234567890",
                "human_value": "3333333333",
                "confidence_score": 0.7,
                "reviewer": "bob",
                "decision": "CORRECTED",
                "origin": "LOW_CONFIDENCE_REVIEW",
            },
            {
                "document_id": doc_b,
                "field_name": "iban",
                "ocr_value": "DE89",
                "human_value": "de89",
                "confidence_score": 0.6,
                "reviewer": "bob",
                "decision": "CORRECTED",
                "origin": "LOW_CONFIDENCE_REVIEW",
            },
            {
                "document_id": doc_b,
                "field_name": "iban",
                "ocr_value": "DE89",
                "human_value": "DE89",
                "confidence_score": 0.5,
                "reviewer": "alice",
                "decision": "CORRECT",
                "origin": "FINAL_HUMAN_REVIEW",
            },
        ],
        application_id=application_id,
    )
    return application_id, {"doc_a": doc_a, "doc_b": doc_b}


def test_all_endpoints_404_on_empty_dataset(authenticated_client):
    assert authenticated_client.get(f"{API}{DATASET_URL}").status_code == 404
    assert authenticated_client.get(f"{API}{STATISTICS_URL}").status_code == 404
    assert authenticated_client.get(f"{API}{EXPORT_JSON_URL}").status_code == 404
    assert authenticated_client.get(f"{API}{EXPORT_CSV_URL}").status_code == 404
    assert authenticated_client.get(f"{API}{VERSION_URL}").status_code == 404


def test_dataset_generation_from_pipeline(authenticated_client, storage_root):
    application_id = build_curated_application(authenticated_client, storage_root)

    response = authenticated_client.get(f"{API}{DATASET_URL}")
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["record_count"] == 2
    assert len(body["records"]) == 2
    for record in body["records"]:
        assert record["application_id"] == application_id
        assert record["document_type"] != "UNKNOWN"
        assert record["field_name"] in {"account_number", "iban"}
        assert record["original_ocr_value"]
        assert record["human_corrected_value"]
        assert record["confidence_score"] == 1.0
        assert record["decision"] == "CORRECT"
        assert record["origin"] == "FINAL_HUMAN_REVIEW"
        assert set(record) == set(CSV_COLUMNS)


def test_dataset_includes_low_confidence_scan(authenticated_client, storage_root, monkeypatch):
    build_curated_application(authenticated_client, storage_root)

    response = authenticated_client.get(f"{API}{DATASET_URL}")
    assert response.status_code == 200
    origins = {record["origin"] for record in response.json()["records"]}
    assert origins == {"FINAL_HUMAN_REVIEW"}


def test_dataset_excludes_invalid_records(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    insert_raw(
        [
            {
                "application_id": application_id,
                "field_name": "account_number",
                "ocr_value": "1234567890",
                "human_value": "1111111111",
                "confidence_score": 0.9,
                "decision": "CORRECT",
            },
            {
                "application_id": None,
                "field_name": "account_number",
                "ocr_value": "1234567890",
                "human_value": "1111111111",
                "confidence_score": 0.9,
            },
            {
                "application_id": application_id,
                "field_name": "iban",
                "ocr_value": "",
                "human_value": "de89",
                "confidence_score": 0.8,
            },
            {
                "application_id": application_id,
                "field_name": "iban",
                "ocr_value": "DE89",
                "human_value": "DE89",
                "confidence_score": 1.5,
            },
            {
                "application_id": application_id,
                "field_name": "iban",
                "ocr_value": "DE89",
                "human_value": "DE89",
                "confidence_score": 0.7,
                "decision": "BOGUS",
            },
        ]
    )

    body = authenticated_client.get(f"{API}{DATASET_URL}").json()
    assert body["metadata"]["record_count"] == 1
    assert body["records"][0]["field_name"] == "account_number"


def test_dataset_excludes_duplicates_keeping_lowest_id(authenticated_client):
    application_id = create_application(authenticated_client)
    recorded_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    insert_raw(
        [
            {
                "application_id": application_id,
                "field_name": "account_number",
                "ocr_value": "1234567890",
                "human_value": "1111111111",
                "confidence_score": 0.9,
                "decision": "CORRECT",
                "recorded_at": recorded_at,
            },
            {
                "application_id": application_id,
                "field_name": "account_number",
                "ocr_value": "1234567890",
                "human_value": "1111111111",
                "confidence_score": 0.9,
                "decision": "CORRECT",
                "recorded_at": recorded_at,
            },
        ]
    )

    body = authenticated_client.get(f"{API}{DATASET_URL}").json()
    assert body["metadata"]["record_count"] == 1
    assert body["records"][0]["human_corrected_value"] == "1111111111"


def test_version_metadata_contract(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)

    metadata = authenticated_client.get(f"{API}{VERSION_URL}").json()
    assert metadata["record_count"] == 2
    assert len(metadata["dataset_hash"]) == 64
    assert int(metadata["dataset_hash"], 16) >= 0
    assert metadata["dataset_version"].startswith("cl-1.0.0-")
    assert len(metadata["dataset_version"]) == len("cl-1.0.0-") + 12
    assert metadata["project_version"] == "0.1.0"
    datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))


def test_hash_is_deterministic_across_calls(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)

    first = authenticated_client.get(f"{API}{DATASET_URL}").json()
    second = authenticated_client.get(f"{API}{DATASET_URL}").json()
    assert first["metadata"]["dataset_hash"] == second["metadata"]["dataset_hash"]
    assert first["metadata"]["dataset_version"] == second["metadata"]["dataset_version"]


def test_hash_matches_canonical_serialization(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)

    body = authenticated_client.get(f"{API}{DATASET_URL}").json()
    records = sorted(body["records"], key=lambda r: r["human_corrected_value"])
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert body["metadata"]["dataset_hash"] == expected


def test_hash_is_stable_across_export_formats(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)

    json_export = authenticated_client.get(f"{API}{EXPORT_JSON_URL}").json()
    csv_export = authenticated_client.get(f"{API}{EXPORT_CSV_URL}").json()
    assert json_export["dataset_hash"] == csv_export["dataset_hash"]
    assert json_export["dataset_version"] == csv_export["dataset_version"]


def test_statistics_aggregation_accuracy(authenticated_client, storage_root):
    five_valid_samples(authenticated_client, storage_root)

    body = authenticated_client.get(f"{API}{STATISTICS_URL}").json()
    assert body["total_records"] == 5
    assert body["document_distribution"] == {
        "ACCOUNT_MAINTENANCE_CERTIFICATE": 3,
        "ONE_LINK_LETTER": 2,
    }
    assert body["field_distribution"] == {"account_number": 3, "iban": 2}
    assert body["correction_distribution"] == {"CORRECT": 3, "CORRECTED": 2}
    assert body["confidence_distribution"] == {
        "0.40-0.60": 1,
        "0.60-0.80": 2,
        "0.80-1.00": 2,
    }
    assert body["average_confidence"] == pytest.approx(0.7)
    assert body["reviewer_distribution"] == {"alice": 3, "bob": 2}


def test_statistics_completeness(authenticated_client, storage_root):
    five_valid_samples(authenticated_client, storage_root)

    body = authenticated_client.get(f"{API}{STATISTICS_URL}").json()
    completeness = body["dataset_completeness"]
    assert completeness["document_type"] == 1.0
    assert completeness["normalized_value"] == 0.0
    assert completeness["confidence_source"] == round(1 / 5, 4)
    assert completeness["correction_reason"] == 0.0
    assert completeness["decision"] == 1.0
    assert completeness["origin"] == 1.0
    assert completeness["reviewer"] == 1.0


def test_statistics_include_export_metadata(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)

    body = authenticated_client.get(f"{API}{STATISTICS_URL}").json()
    metadata = body["metadata"]
    assert metadata["record_count"] == 2
    assert len(metadata["dataset_hash"]) == 64
    assert metadata["dataset_version"].startswith("cl-1.0.0-")


def test_json_export(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)

    body = authenticated_client.get(f"{API}{EXPORT_JSON_URL}").json()
    assert body["format"] == "json"
    assert body["record_count"] == 2
    assert body["dataset_hash"]
    assert body["dataset_version"].startswith("cl-1.0.0-")
    assert body["project_version"] == "0.1.0"
    assert body["filename"].startswith("continuous_learning_dataset_")
    assert body["filename"].endswith(".json")
    records = json.loads(body["content"])
    assert len(records) == 2
    for record in records:
        assert record["original_ocr_value"]
        assert record["human_corrected_value"]
        assert 0.0 <= record["confidence_score"] <= 1.0


def test_csv_export_header_and_rows(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)

    body = authenticated_client.get(f"{API}{EXPORT_CSV_URL}").json()
    assert body["format"] == "csv"
    assert body["record_count"] == 2
    assert body["filename"].endswith(".csv")
    parsed = list(csv.DictReader(io.StringIO(body["content"])))
    assert parsed[0].keys() == set(CSV_COLUMNS) == set(parsed[0])
    assert len(parsed) == 2
    assert all(row["human_corrected_value"] for row in parsed)
    assert all(row["application_id"] for row in parsed)


def test_dataset_records_sorted_deterministically(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)

    first = authenticated_client.get(f"{API}{DATASET_URL}").json()
    second = authenticated_client.get(f"{API}{DATASET_URL}").json()
    assert [r["recorded_at"] for r in first["records"]] == [
        r["recorded_at"] for r in second["records"]
    ]


def test_dataset_after_pipeline_and_invalid_mix(authenticated_client, storage_root):
    build_curated_application(authenticated_client, storage_root)
    application_id = create_application(authenticated_client)
    insert_raw(
        [
            {
                "application_id": application_id,
                "field_name": "account_number",
                "ocr_value": "",
                "human_value": "1111111111",
                "confidence_score": 0.9,
            }
        ]
    )

    body = authenticated_client.get(f"{API}{DATASET_URL}").json()
    assert body["metadata"]["record_count"] == 2
