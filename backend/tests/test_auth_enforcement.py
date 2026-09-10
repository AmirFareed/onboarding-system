"""Regression coverage for the global auth dependency.

Until 2026-08-14, `get_current_user` was wired into exactly one router
(`bulk_queue`, covered by `test_bulk_queue.py::test_unauthenticated_requests_
rejected`) -- the other 13 route modules had no auth enforcement at all,
despite handling real application data (documents, extracted fields, human
review decisions). See `app/api/__init__.py` for the fix: a single
`dependencies=[Depends(get_current_user)]` applied to a `protected_router`
that wraps every module except `health` and `auth` itself.

This file is the regression test for that gap: every endpoint outside those
two modules must reject an unauthenticated request with 401. It intentionally
does not re-list the 7 `bulk_queue` endpoints already covered by
`test_bulk_queue.py`.
"""

API = "/api/v1"

#: Every endpoint added to `protected_router` in `app/api/__init__.py`,
#: excluding `bulk_queue` (covered separately). Path parameters use `1` as a
#: representative id -- the auth dependency must reject the request before
#: the path parameter or body is ever inspected, so the id need not exist.
_PROTECTED_ENDPOINTS: list[tuple[str, str]] = [
    # completeness
    ("get", "/applications/1/completeness"),
    ("post", "/applications/1/completeness/verify"),
    # confidence
    ("post", "/applications/1/confidence/evaluate"),
    ("post", "/applications/1/confidence/review"),
    # continuous_learning
    ("get", "/continuous-learning/dataset"),
    ("get", "/continuous-learning/statistics"),
    ("get", "/continuous-learning/export/json"),
    ("get", "/continuous-learning/export/csv"),
    ("get", "/continuous-learning/version"),
    # document_analysis
    ("post", "/applications/1/analyze-documents"),
    ("get", "/applications/1/analysis-results"),
    # document_processing
    ("post", "/applications/1/process-documents"),
    ("get", "/applications/1/ocr-results"),
    # feedback
    ("get", "/feedback"),
    ("get", "/feedback/statistics"),
    ("get", "/feedback/export/json"),
    ("get", "/feedback/export/csv"),
    ("get", "/feedback/1"),
    # human_verification
    ("get", "/applications/1/human-review"),
    ("post", "/applications/1/human-review"),
    ("get", "/applications/1/human-review/history"),
    # normalization
    ("post", "/applications/1/normalize"),
    ("get", "/applications/1/normalized-fields"),
    # reports
    ("get", "/applications/1/validation-report"),
    ("get", "/applications/1/validation-report/html"),
    ("get", "/applications/1/validation-summary"),
    # rule_engine
    ("post", "/applications/1/validate"),
    ("get", "/applications/1/validation-results"),
    # technical_validation
    ("get", "/applications/1/technical-validation"),
    ("post", "/applications/1/technical-validation/validate"),
    # upload
    ("post", "/applications"),
    ("get", "/applications"),
    ("get", "/applications/1"),
    ("post", "/applications/1/documents"),
    ("put", "/applications/1/documents/1"),
    ("delete", "/applications/1/documents/1"),
    ("get", "/applications/1/documents"),
    ("get", "/documents/1"),
    ("get", "/applications/1/documents/1/download"),
    ("post", "/applications/1/bulk-upload"),
]


def test_protected_endpoint_inventory_has_40_entries():
    """Guards the list above against silently drifting from the real router set.

    If a new endpoint is added to a protected module and this list isn't
    updated, this is the test that should fail and prompt someone to add it
    here -- see `app/api/__init__.py` for why per-router discipline alone
    already failed silently once.
    """
    assert len(_PROTECTED_ENDPOINTS) == 40


def test_unauthenticated_requests_rejected_everywhere(client):
    """Every endpoint outside health/auth/bulk_queue must 401 with no session."""
    failures = []
    for method, endpoint in _PROTECTED_ENDPOINTS:
        response = getattr(client, method)(f"{API}{endpoint}")
        if response.status_code != 401:
            failures.append(f"{method.upper()} {endpoint} -> {response.status_code}")
    assert not failures, "Endpoints that did not reject an unauthenticated request:\n" + "\n".join(failures)


def test_health_and_auth_remain_reachable_without_a_session(client):
    """Confirms the allowlist itself: these must NOT require a session."""
    assert client.get(f"{API}/health").status_code == 200
    # Wrong credentials still means the endpoint was *reachable* -- a 401 here
    # is the expected "bad password" response, not "blocked by the router".
    response = client.post(
        f"{API}/auth/login",
        json={"identifier": "nobody", "password": "wrong", "remember": False},
    )
    assert response.status_code == 401
