"""Unit tests for the FastAPI Web UI, API print endpoint, preview endpoint, and SMS webhook."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lp2443_printer.config import PrinterSettings
from lp2443_printer.server import create_app


def test_web_ui_and_preview_endpoints(tmp_path: Path) -> None:
    dummy_dev = tmp_path / "dummy_lp0"
    dummy_dev.write_bytes(b"")
    cfg = PrinterSettings(device_path=str(dummy_dev), api_key="secret123")
    app = create_app(cfg)
    client = TestClient(app)

    # 1. Web UI
    res = client.get("/")
    assert res.status_code == 200
    assert "LP2443PSA Label Messenger" in res.text

    # 2. Status endpoint
    status_res = client.get("/api/status")
    assert status_res.status_code == 200
    assert status_res.json()["connected"] is True

    # 3. Preview PNG endpoint
    prev_res = client.get("/api/preview", params={"message": "Hello Test", "sender": "Pytest"})
    assert prev_res.status_code == 200
    assert prev_res.headers["content-type"] == "image/png"
    assert prev_res.content.startswith(b"\x89PNG")


def test_api_print_and_auth_and_sms_webhook(tmp_path: Path) -> None:
    dummy_dev = tmp_path / "dummy_lp0"
    dummy_dev.write_bytes(b"")
    cfg = PrinterSettings(device_path=str(dummy_dev), api_key="secret123")
    app = create_app(cfg)
    client = TestClient(app)

    # Unauthorized without API key
    unauth = client.post("/api/print", json={"message": "Hello"})
    assert unauth.status_code == 401

    # Authorized with X-API-Key header
    ok_res = client.post(
        "/api/print",
        headers={"X-API-Key": "secret123"},
        json={"message": "Print via API", "sender": "Jake"},
    )
    assert ok_res.status_code == 200
    data = ok_res.json()
    assert data["ok"] is True
    assert data["bytes_written"] > 100000

    # Verify dummy device received valid EPL2 GW payload
    written_bytes = dummy_dev.read_bytes()
    assert b"\nN\nq812\nQ1218,24\nS1\nD15\n" in written_bytes
    assert written_bytes.endswith(b"\nP1\n")

    # Test Twilio SMS Webhook with ?token= query param
    sms_res = client.post(
        "/webhook/sms?token=secret123",
        data={"Body": "Text from Twilio!", "From": "+15551234567"},
    )
    assert sms_res.status_code == 200
    assert "<Response></Response>" in sms_res.text
