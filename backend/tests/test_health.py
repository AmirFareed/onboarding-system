"""Tests for /health's database and worker-heartbeat checks."""

from __future__ import annotations

import time

from app.core.config import get_settings

API = "/api/v1"


def test_health_degraded_when_heartbeat_file_missing(client):
    """No heartbeat file (e.g. dev mode with no dedicated worker process) degrades."""
    settings = get_settings()
    # Default worker_heartbeat_path points at a file that does not exist in a
    # clean test environment; assert that explicitly rather than assuming it.
    assert not settings.worker_heartbeat_path.exists()

    response = client.get(f"{API}/health")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ok"
    assert data["degraded"] is True
    assert data["details"]["worker"] == "Queue worker heartbeat stale or missing"


def test_health_degraded_when_heartbeat_stale(client, monkeypatch, tmp_path):
    """A heartbeat older than 60 seconds is treated the same as missing."""
    settings = get_settings()
    heartbeat_path = tmp_path / "worker.heartbeat"
    heartbeat_path.write_text(str(time.time() - 120))
    monkeypatch.setattr(settings, "worker_heartbeat_path", heartbeat_path)

    response = client.get(f"{API}/health")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ok"
    assert data["degraded"] is True
    assert data["details"]["worker"] == "Queue worker heartbeat stale or missing"


def test_health_ok_when_heartbeat_fresh(client, monkeypatch, tmp_path):
    """A recently written heartbeat reports a fully healthy status."""
    settings = get_settings()
    heartbeat_path = tmp_path / "worker.heartbeat"
    heartbeat_path.write_text(str(time.time()))
    monkeypatch.setattr(settings, "worker_heartbeat_path", heartbeat_path)

    response = client.get(f"{API}/health")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data == {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": data["version"],
    }


def test_health_degraded_when_heartbeat_file_corrupt(client, monkeypatch, tmp_path):
    """Unparseable heartbeat contents degrade rather than raising a 500."""
    settings = get_settings()
    heartbeat_path = tmp_path / "worker.heartbeat"
    heartbeat_path.write_text("not-a-timestamp")
    monkeypatch.setattr(settings, "worker_heartbeat_path", heartbeat_path)

    response = client.get(f"{API}/health")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["degraded"] is True
