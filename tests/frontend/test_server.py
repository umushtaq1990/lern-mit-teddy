"""Smoke tests for the FastAPI app wiring — health, metrics, request-id header."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.frontend.server import app


def test_health_endpoint():
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_metrics_endpoint_exposed():
    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"http_requests_total" in resp.content or b"# HELP" in resp.content


def test_request_id_header_present():
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert "x-request-id" in resp.headers
