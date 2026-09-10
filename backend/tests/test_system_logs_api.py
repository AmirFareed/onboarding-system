"""Tests for the IT system-log API.

The system-log API is read-only operational audit access for the IT role:
searchable/filterable/paginated access to the shared audit log. Tests cover the
IT-only role guard (403 for other roles), the search filters, pagination and
the single-entry endpoint.
"""

from app.database.connection import SessionLocal
from app.database.repositories.audit_log_repository import AuditLogRepository
from tests.test_technical_validation_api import create_application_direct

API = "/api/v1"

SYSTEM_LOGS_URL = "/system-logs"


def _record_audit_entries(application_id: int) -> None:
    """Write a couple of audit log entries directly via the repository."""
    db = SessionLocal()
    try:
        logs = AuditLogRepository(db)
        logs.create(
            application_id=application_id,
            username="operator.one",
            action="DOCUMENTS_REQUESTED",
            details={"missing_document_types": ["ONE_LINK_LETTER"]},
            actor_role="OPERATOR",
            severity="WARNING",
            previous_status="SUBMITTED",
            new_status="NEEDS_DOCUMENTS",
        )
        logs.create(
            application_id=application_id,
            username="it.support",
            action="LOGIN",
            details={},
            actor_role="IT",
            severity="INFO",
        )
    finally:
        db.close()


# --- Role enforcement -------------------------------------------------------


def test_system_logs_require_it_role(reviewer_client):
    """Non-IT roles receive 403 on the system-log endpoints."""
    response = reviewer_client.get(f"{API}{SYSTEM_LOGS_URL}")
    assert response.status_code == 403, response.text


def test_system_logs_require_it_role_for_operator(operator_client):
    """Operators receive 403 on the system-log endpoints."""
    response = operator_client.get(f"{API}{SYSTEM_LOGS_URL}")
    assert response.status_code == 403, response.text


def test_system_logs_require_authentication(client):
    """Unauthenticated requests to system logs are rejected (401)."""
    response = client.get(f"{API}{SYSTEM_LOGS_URL}")
    assert response.status_code == 401, response.text


# --- Search -----------------------------------------------------------------


def test_system_logs_lists_newest_first(it_client):
    """Log entries are returned newest first with pagination metadata."""
    application_id = create_application_direct()
    _record_audit_entries(application_id)
    response = it_client.get(f"{API}{SYSTEM_LOGS_URL}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2
    assert payload["offset"] == 0
    assert payload["limit"] == 50
    actions = [item["action"] for item in payload["items"]]
    assert actions == ["LOGIN", "DOCUMENTS_REQUESTED"]
    assert payload["items"][0]["actor_role"] == "IT"


def test_system_logs_filter_by_application(it_client):
    """Filtering by application id returns only that application's logs."""
    app_a = create_application_direct()
    _record_audit_entries(app_a)
    app_b = create_application_direct()
    _record_audit_entries(app_b)
    response = it_client.get(f"{API}{SYSTEM_LOGS_URL}", params={"application_id": app_a})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2
    for item in payload["items"]:
        assert item["application_id"] == app_a


def test_system_logs_filter_by_action(it_client):
    """Filtering by event type/action returns only matching logs."""
    application_id = create_application_direct()
    _record_audit_entries(application_id)
    response = it_client.get(
        f"{API}{SYSTEM_LOGS_URL}",
        params={"event_type": "DOCUMENTS_REQUESTED"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["action"] == "DOCUMENTS_REQUESTED"


def test_system_logs_filter_by_actor(it_client):
    """Filtering by actor returns only logs from that username."""
    application_id = create_application_direct()
    _record_audit_entries(application_id)
    response = it_client.get(f"{API}{SYSTEM_LOGS_URL}", params={"actor": "it.support"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["username"] == "it.support"


def test_system_logs_filter_by_severity(it_client):
    """Filtering by severity returns only logs at that severity."""
    application_id = create_application_direct()
    _record_audit_entries(application_id)
    response = it_client.get(f"{API}{SYSTEM_LOGS_URL}", params={"severity": "WARNING"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["severity"] == "WARNING"


def test_system_logs_pagination(it_client):
    """Limit/offset paginate correctly over the newest-first ordering."""
    application_id = create_application_direct()
    _record_audit_entries(application_id)
    _record_audit_entries(application_id)
    response = it_client.get(f"{API}{SYSTEM_LOGS_URL}", params={"limit": 2, "offset": 2})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 4
    assert len(payload["items"]) == 2


# --- Orphaned entries (application deleted, ON DELETE SET NULL) ------------


def _record_orphaned_entry() -> None:
    """Write an audit log entry with no linked application, directly via the
    repository -- the same shape a real entry ends up in once the
    application it was recorded against is later deleted."""
    db = SessionLocal()
    try:
        AuditLogRepository(db).create(
            application_id=None,
            username="system",
            action="confidence.evaluated",
            details={"status": "READY_FOR_NORMALIZATION"},
        )
    finally:
        db.close()


def test_system_logs_hides_orphaned_entries_by_default(it_client):
    """Entries with no linked application are excluded unless asked for.

    Regression test for a real finding (2026-08-23/24): a dev database with
    heavy test-application churn accumulates a large number of orphaned
    audit-log rows (applications get deleted, ``ON DELETE SET NULL`` keeps
    the audit trail but drops the link) that flood this view with entries an
    IT reviewer can't act on -- confirmed on the real dev DB as 99.97% of all
    rows. The default must stay clean without dropping anything real.
    """
    application_id = create_application_direct()
    _record_audit_entries(application_id)
    _record_orphaned_entry()
    response = it_client.get(f"{API}{SYSTEM_LOGS_URL}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2
    assert all(item["application_id"] is not None for item in payload["items"])


def test_system_logs_include_orphaned_shows_everything(it_client):
    """``include_orphaned=true`` opts back into seeing every entry."""
    application_id = create_application_direct()
    _record_audit_entries(application_id)
    _record_orphaned_entry()
    response = it_client.get(
        f"{API}{SYSTEM_LOGS_URL}", params={"include_orphaned": True}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert any(item["application_id"] is None for item in payload["items"])


# --- Single entry -----------------------------------------------------------


def test_system_log_get_single_entry(it_client):
    """The single-entry endpoint returns the full stored log record."""
    application_id = create_application_direct()
    _record_audit_entries(application_id)
    db = SessionLocal()
    try:
        logs, _ = AuditLogRepository(db).search(application_id=application_id)
        log_id = logs[0].id
    finally:
        db.close()
    response = it_client.get(f"{API}{SYSTEM_LOGS_URL}/{log_id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == log_id
    assert payload["application_id"] == application_id


def test_system_log_get_missing_entry(it_client):
    """Requesting a nonexistent log entry returns 404."""
    response = it_client.get(f"{API}{SYSTEM_LOGS_URL}/999999")
    assert response.status_code == 404, response.text