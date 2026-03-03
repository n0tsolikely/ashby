from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app


@pytest.mark.asyncio
async def test_api_registry_success_envelope():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.get("/api/registry")
    finally:
        await c.aclose()
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert isinstance(data.get("trace"), dict)
    assert isinstance(data["trace"].get("request_id"), str)


@pytest.mark.asyncio
async def test_api_sessions_list_success_envelope(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.get("/api/sessions")
    finally:
        await c.aclose()
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert isinstance(data.get("sessions"), list)
    assert isinstance(data.get("page"), dict)


@pytest.mark.asyncio
async def test_api_run_error_envelope_on_missing_fields():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.post("/api/run", json={})
    finally:
        await c.aclose()
    assert r.status_code == 400
    data = r.json()
    assert data.get("ok") is False
    assert isinstance(data.get("error"), dict)
    assert data["error"].get("code") == "INVALID_REQUEST"
    assert isinstance(data.get("trace"), dict)


@pytest.mark.asyncio
async def test_api_chat_global_returns_chat_envelope():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.post("/api/chat/global", json={"text": "hello", "ui": {}})
    finally:
        await c.aclose()
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert isinstance(data.get("reply"), dict)
    assert isinstance(data["reply"].get("text"), str)
    assert isinstance(data["reply"].get("hits"), list)
