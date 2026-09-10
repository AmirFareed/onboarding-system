"""Tests for the feedback API.

End-to-end tests build feedback samples through the real pipeline (a
low-confidence review that corrects a scanned statement and a final review that
corrects a validated application) and through direct repository inserts for
precise aggregation checks. The tests cover listing, pagination, every filter,
single-entry retrieval, 404 handling, deterministic statistics, JSON/CSV export
and empty/large datasets.
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database.connection import SessionLocal
from app.database.models.enums import DocumentType
from app.database.models.feedback_dataset import FeedbackEntry
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.feedback_repository import FeedbackRepository
from app.feedback.constants import CSV_COLUMNS
from tests.test_confidence_api import (
    add_scanned_statement,
    add_digital_statement,
    evaluate,
    review,
    stored_fields,
)
from tests.test_document_analysis_api import add_digital_pdf
from tests.test_reports_api import build_single_statement_application
from tests.test_technical_validation_api import create_application

API = "/api/v1"

LIST_URL = "/feedback"
STATISTICS_URL = "/feedback/statistics"
EXPORT_JSON_URL = "/feedback/export/json"
EXPORT_CSV_URL = "/feedback/export/csv"


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


def feedback_rows(application_id: int | None = None) -> list[FeedbackEntry]:
    """Return feedback rows, optionally narrowed to one application."""
    db = SessionLocal()
    try:
        query = db.query(FeedbackEntry)
        if application_id is not None:
            query = query.filter_by(application_id=application_id)
        return query.order_by(FeedbackEntry.id).all()
    finally:
        db.close()


def insert_feedback(rows: list[dict], *, application_id: int) -> list[int]:
    """Insert feedback samples via the repository; return their ids."""
    db = SessionLocal()
    try:
        repository = FeedbackRepository(db)
        return [
            repository.create(application_id=application_id, **row).id for row in rows
        ]
    finally:
        db.close()


def final_correct_review(client, application_id: int):
    """Submit a CORRECT final review that changes two fields."""
    fields = stored_fields(application_id)
    return client.post(
        f"{API}/applications/{application_id}/human-review",
        json={
            "decision": "CORRECT",
            "corrections": [
                {
                    "field_name": "account_number",
                    "corrected_value": "9999999999",
                    "reason": "reviewer fixed the account number",
                },
                {
                    "field_name": "iban",
                    "corrected_value": "xx00 0000 0000 0000 00",
                    "reason": "reviewer fixed the iban",
                },
            ],
        },
    )


def low_confidence_corrected(client, storage_root, monkeypatch) -> int:
    """Build a scanned statement and correct one field in the low-confidence review."""
    application_id = add_scanned_statement(client, storage_root, monkeypatch)
    flagged = evaluate(client, application_id)["fields_requiring_review"]
    decisions = [
        {
            "field_name": field["field_name"],
            "decision": "VERIFIED",
        }
        for field in flagged
        if field["field_name"] != "account_number"
    ]
    decisions.append(
        {
            "field_name": "account_number",
            "decision": "CORRECTED",
            "corrected_value": "7777777777",
        }
    )
    response = review(client, application_id, decisions)
    assert response["processing_status"] == "READY_FOR_NORMALIZATION"
    return application_id


# --- Listing and pagination --------------------------------------------------


def test_list_feedback_empty(authenticated_client):
    response = authenticated_client.get(f"{API}{LIST_URL}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["returned"] == 0
    assert body["items"] == []


def test_list_feedback_returns_all_entries_newest_first(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    assert final_correct_review(authenticated_client, application_id).status_code == 200

    response = authenticated_client.get(f"{API}{LIST_URL}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["returned"] == 2
    recorded_ats = [item["recorded_at"] for item in body["items"]]
    assert recorded_ats == sorted(recorded_ats, reverse=True)


def test_list_feedback_pagination(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    insert_feedback(
        [
            {"field_name": f"field_{index}", "human_value": f"v{index}", "ocr_value": f"o{index}"}
            for index in range(5)
        ],
        application_id=application_id,
    )

    first = authenticated_client.get(f"{API}{LIST_URL}?offset=0&limit=2").json()
    assert first["total"] == 5
    assert first["returned"] == 2

    second = authenticated_client.get(f"{API}{LIST_URL}?offset=2&limit=2").json()
    assert second["returned"] == 2

    third = authenticated_client.get(f"{API}{LIST_URL}?offset=4&limit=2").json()
    assert third["returned"] == 1

    combined = [item["id"] for item in first["items"] + second["items"] + third["items"]]
    assert len(set(combined)) == 5


def test_list_feedback_limits_are_enforced(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    insert_feedback(
        [{"field_name": f"f{i}", "human_value": "h", "ocr_value": "o"} for i in range(3)],
        application_id=application_id,
    )
    response = authenticated_client.get(f"{API}{LIST_URL}?limit=501")
    assert response.status_code == 422


# --- Filtering ---------------------------------------------------------------


def test_filter_by_application(authenticated_client, storage_root):
    application_a = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_a)
    application_b = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_b)

    body = authenticated_client.get(f"{API}{LIST_URL}?application_id={application_a}").json()
    assert body["total"] == 2
    assert all(item["application_id"] == application_a for item in body["items"])


def test_filter_by_field_name(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)

    body = authenticated_client.get(f"{API}{LIST_URL}?field_name=iban").json()
    assert body["total"] == 1
    assert body["items"][0]["field_name"] == "iban"


def test_filter_by_decision(authenticated_client, storage_root, monkeypatch):
    low_confidence_corrected(authenticated_client, storage_root, monkeypatch)

    corrected = authenticated_client.get(f"{API}{LIST_URL}?decision=CORRECTED").json()
    assert corrected["total"] == 1
    assert corrected["items"][0]["decision"] == "CORRECTED"


def test_filter_by_reviewer(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)

    body = authenticated_client.get(f"{API}{LIST_URL}?reviewer=Test+Operator").json()
    assert body["total"] == 2
    assert all(item["reviewer"] == "Test Operator" for item in body["items"])
    assert authenticated_client.get(f"{API}{LIST_URL}?reviewer=nobody").json()["total"] == 0


def test_filter_by_document_type(authenticated_client, storage_root, monkeypatch):
    application_id = low_confidence_corrected(authenticated_client, storage_root, monkeypatch)
    document_type = DocumentRepository(SessionLocal()).get_by_application(application_id)[
        0
    ].document_type

    body = authenticated_client.get(f"{API}{LIST_URL}?document_type={document_type.value}").json()
    assert body["total"] == 1
    assert body["items"][0]["field_name"] == "account_number"


def test_filter_by_date_range(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)
    now = datetime.now(timezone.utc)

    def iso(instant: datetime) -> str:
        return instant.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_rows = authenticated_client.get(
        f"{API}{LIST_URL}?date_from={iso(now - timedelta(hours=1))}&date_to={iso(now + timedelta(hours=1))}"
    ).json()
    assert all_rows["total"] == 2

    future_only = authenticated_client.get(
        f"{API}{LIST_URL}?date_from={iso(now + timedelta(hours=1))}"
    ).json()
    assert future_only["total"] == 0

    past_only = authenticated_client.get(
        f"{API}{LIST_URL}?date_to={iso(now - timedelta(hours=1))}"
    ).json()
    assert past_only["total"] == 0


def test_filter_by_min_confidence(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)

    body = authenticated_client.get(f"{API}{LIST_URL}?min_confidence=0.99").json()
    assert body["total"] == 2
    assert all(item["confidence_score"] == 1.0 for item in body["items"])


def test_filter_combined(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)

    body = authenticated_client.get(
        f"{API}{LIST_URL}?application_id={application_id}&decision=CORRECT&field_name=account_number"
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["field_name"] == "account_number"

    none_match = authenticated_client.get(
        f"{API}{LIST_URL}?application_id={application_id}&decision=CORRECT&field_name=amount"
    ).json()
    assert none_match["total"] == 0


def test_inverted_date_range_returns_422(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    insert_feedback(
        [{"field_name": "f", "human_value": "h", "ocr_value": "o"}],
        application_id=application_id,
    )
    response = authenticated_client.get(
        f"{API}{LIST_URL}?date_from=2027-01-01T00:00:00Z&date_to=2026-01-01T00:00:00Z"
    )
    assert response.status_code == 422


def test_unknown_decision_filter_returns_422(authenticated_client):
    response = authenticated_client.get(f"{API}{LIST_URL}?decision=BOGUS")
    assert response.status_code == 422


def test_out_of_range_confidence_returns_422(authenticated_client):
    response = authenticated_client.get(f"{API}{LIST_URL}?min_confidence=1.5")
    assert response.status_code == 422


# --- Single entry ------------------------------------------------------------


def test_get_feedback_by_id_exposes_14_fields(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)
    entry_id = feedback_rows(application_id)[0].id

    response = authenticated_client.get(f"{API}{LIST_URL}/{entry_id}")
    assert response.status_code == 200
    item = response.json()
    assert set(item) == set(CSV_COLUMNS)
    assert item["id"] == entry_id
    assert item["application_id"] == application_id
    assert item["document_id"] is not None
    assert item["ocr_result_id"] is not None
    assert item["field_name"] in {"account_number", "iban"}
    assert item["human_corrected_value"]
    assert item["reviewer"] == "Test Operator"
    assert item["decision"] == "CORRECT"
    assert item["origin"] == "FINAL_HUMAN_REVIEW"
    assert item["correction_reason"]


def test_get_feedback_returns_404(authenticated_client):
    response = authenticated_client.get(f"{API}{LIST_URL}/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Feedback entry not found"


# --- Statistics --------------------------------------------------------------


def test_statistics_empty(authenticated_client):
    body = authenticated_client.get(f"{API}{STATISTICS_URL}").json()
    assert body["total_entries"] == 0
    assert body["total_corrected_fields"] == 0
    assert body["most_corrected_fields"] == []
    assert body["average_confidence"] is None
    assert body["corrections_by_reviewer"] == {}
    assert body["corrections_by_document_type"] == {}
    assert body["corrections_by_decision"] == {}
    assert body["correction_frequency"] == []
    assert "generated_at" in body


def test_statistics_over_pipeline_data(authenticated_client, storage_root, monkeypatch):
    final_app = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, final_app)
    low_app = low_confidence_corrected(authenticated_client, storage_root, monkeypatch)

    body = authenticated_client.get(f"{API}{STATISTICS_URL}").json()
    assert body["total_entries"] == 3
    assert body["total_corrected_fields"] == 3
    assert body["corrections_by_decision"] == {"CORRECT": 2, "CORRECTED": 1}
    assert body["corrections_by_reviewer"] == {"Test Operator": 3}
    assert body["corrections_by_document_type"] == {
        "ACCOUNT_MAINTENANCE_CERTIFICATE": 2,
        # low_confidence_corrected() -> add_scanned_statement() in
        # test_confidence_api.py, swapped from ONE_LINK_LETTER to
        # SCHEDULE_OF_CHARGES once ONE_LINK_LETTER got a real extractor.
        "SCHEDULE_OF_CHARGES": 1,
    }
    assert body["average_confidence"] is not None
    assert {item["field_name"] for item in body["most_corrected_fields"]} == {
        "account_number",
        "iban",
    }


def test_statistics_aggregation_accuracy(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
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
        d.id for d in documents if d.document_type is DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
    )
    doc_b = next(d.id for d in documents if d.document_type is DocumentType.ONE_LINK_LETTER)

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

    body = authenticated_client.get(f"{API}{STATISTICS_URL}").json()
    assert body["total_entries"] == 5
    assert body["total_corrected_fields"] == 4
    assert body["average_confidence"] == pytest.approx(0.725)
    assert body["most_corrected_fields"] == [
        {"field_name": "account_number", "count": 3},
        {"field_name": "iban", "count": 2},
    ]
    assert body["corrections_by_reviewer"] == {"alice": 3, "bob": 2}
    assert body["corrections_by_document_type"] == {
        "ACCOUNT_MAINTENANCE_CERTIFICATE": 3,
        "ONE_LINK_LETTER": 2,
    }
    assert body["corrections_by_decision"] == {"CORRECT": 3, "CORRECTED": 2}
    assert len(body["correction_frequency"]) == 1
    assert body["correction_frequency"][0]["count"] == 5


def test_statistics_can_be_filtered(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)

    body = authenticated_client.get(f"{API}{STATISTICS_URL}?field_name=iban").json()
    assert body["total_entries"] == 1
    assert body["corrections_by_decision"] == {"CORRECT": 1}


def test_statistics_large_dataset_is_deterministic(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    rows = [
        {
            "field_name": f"field_{index % 3}",
            "ocr_value": f"o{index}",
            "human_value": f"h{index}",
            "confidence_score": 0.1 + (index % 10) / 10,
            "reviewer": f"reviewer_{index % 2}",
            "decision": "CORRECTED",
            "origin": "LOW_CONFIDENCE_REVIEW",
        }
        for index in range(200)
    ]
    insert_feedback(rows, application_id=application_id)

    body = authenticated_client.get(f"{API}{STATISTICS_URL}").json()
    assert body["total_entries"] == 200
    assert body["total_corrected_fields"] == 200
    assert [item["count"] for item in body["most_corrected_fields"]] == [67, 67, 66]
    expected_average = sum(0.1 + (index % 10) / 10 for index in range(200)) / 200
    assert body["average_confidence"] == pytest.approx(expected_average)
    assert body["corrections_by_reviewer"] == {"reviewer_0": 100, "reviewer_1": 100}

    again = authenticated_client.get(f"{API}{STATISTICS_URL}").json()
    assert {key: value for key, value in again.items() if key != "generated_at"} == {
        key: value for key, value in body.items() if key != "generated_at"
    }


# --- Exports ----------------------------------------------------------------


def test_export_json(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)

    response = authenticated_client.get(f"{API}{EXPORT_JSON_URL}")
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "json"
    assert body["record_count"] == 2
    assert body["filename"].endswith(".json")
    records = json.loads(body["content"])
    assert len(records) == 2
    assert set(records[0]) == set(CSV_COLUMNS)
    assert records[0]["origin"] == "FINAL_HUMAN_REVIEW"


def test_export_csv(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)

    response = authenticated_client.get(f"{API}{EXPORT_CSV_URL}")
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "csv"
    assert body["record_count"] == 2
    assert body["filename"].endswith(".csv")
    parsed = list(csv.DictReader(io.StringIO(body["content"])))
    assert parsed[0].keys() == set(CSV_COLUMNS)
    assert len(parsed) == 2
    assert {row["field_name"] for row in parsed} == {"account_number", "iban"}


def test_export_respects_filters(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)
    final_correct_review(authenticated_client, application_id)

    body = authenticated_client.get(f"{API}{EXPORT_CSV_URL}?field_name=account_number").json()
    assert body["record_count"] == 1
    parsed = list(csv.DictReader(io.StringIO(body["content"])))
    assert len(parsed) == 1
    assert parsed[0]["field_name"] == "account_number"


def test_export_empty_dataset(authenticated_client):
    json_body = authenticated_client.get(f"{API}{EXPORT_JSON_URL}").json()
    assert json_body["record_count"] == 0
    assert json.loads(json_body["content"]) == []

    csv_body = authenticated_client.get(f"{API}{EXPORT_CSV_URL}").json()
    assert csv_body["record_count"] == 0
    assert csv_body["content"].strip() == ",".join(CSV_COLUMNS)


def test_pipeline_enriches_feedback_provenance(authenticated_client, storage_root, monkeypatch):
    application_id = low_confidence_corrected(authenticated_client, storage_root, monkeypatch)
    entry = feedback_rows(application_id)[0]
    assert entry.document_id is not None
    assert entry.ocr_result_id is not None
    assert entry.reviewer == "Test Operator"
    assert entry.decision == "CORRECTED"
    assert entry.origin == "LOW_CONFIDENCE_REVIEW"
