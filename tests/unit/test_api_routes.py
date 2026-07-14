"""Unit tests for src/api/routes.py — HTTP-level validation and health endpoint."""
from fastapi.testclient import TestClient

import app as app_module


client = TestClient(app_module.app)


# Task 13.5 / 19.7 — test_invalid_file_type, test_file_too_large, test_health_endpoint
def test_invalid_file_type_rejected():
    response = client.post(
        "/extract",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        data={"fields": "Name", "output_format": "json"},
    )
    assert response.status_code == 400


def test_file_too_large_rejected(monkeypatch):
    # Temporarily shrink the max upload size so a small payload counts as "too large".
    original_max = app_module.settings.max_upload_bytes
    monkeypatch.setattr(app_module.settings, "max_upload_bytes", 10)

    try:
        response = client.post(
            "/extract",
            files={"file": ("doc.pdf", b"%PDF-1.4 " + b"x" * 100, "application/pdf")},
            data={"fields": "Name", "output_format": "json"},
        )
        assert response.status_code == 413
    finally:
        monkeypatch.setattr(app_module.settings, "max_upload_bytes", original_max)


def test_health_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mistral_key_present"] is True


def test_extract_rejects_empty_fields():
    response = client.post(
        "/extract",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"fields": "   ", "output_format": "json"},
    )
    assert response.status_code == 400


def test_extract_rejects_invalid_output_format():
    response = client.post(
        "/extract",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"fields": "Name", "output_format": "xml"},
    )
    assert response.status_code == 400


def test_index_page_renders():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
