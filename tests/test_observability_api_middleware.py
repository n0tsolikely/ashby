from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import ashby.interfaces.web.app as app_module


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        rows.append(json.loads(ln))
    return rows


@pytest.mark.asyncio
async def test_middleware_emits_request_response_and_startup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_rt"))

    app = app_module.create_app()
    client = None
    await app.router.startup()
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
        res = await client.get("/api/registry", headers={"X-Correlation-Id": "cid-mid-1"})
        assert res.status_code == 200
    finally:
        if client is not None:
            await client.aclose()
        await app.router.shutdown()

    events_path = tmp_path / "stuart_rt" / "realtime_log" / "events.jsonl"
    rows = _read_jsonl(events_path)
    names = [r.get("event") for r in rows]

    assert "system.start" in names
    assert "api.request_received" in names
    assert "api.response_sent" in names

    req_rows = [r for r in rows if r.get("event") == "api.request_received"]
    resp_rows = [r for r in rows if r.get("event") == "api.response_sent"]
    assert req_rows and resp_rows
    assert req_rows[-1]["correlation_id"] == "cid-mid-1"
    assert resp_rows[-1]["correlation_id"] == "cid-mid-1"
    assert isinstance(resp_rows[-1].get("duration_ms"), int)


@pytest.mark.asyncio
async def test_middleware_emits_api_error_and_backend_alert(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_rt"))

    original = app_module.registry_payload

    def _boom():
        raise RuntimeError("boom sk-abc123456789")

    monkeypatch.setattr(app_module, "registry_payload", _boom)
    client = None
    try:
        app = app_module.create_app()
        await app.router.startup()
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
        res = await client.get("/api/registry", headers={"X-Correlation-Id": "cid-mid-err"})
        assert res.status_code == 500
    finally:
        if client is not None:
            await client.aclose()
        await app.router.shutdown()
        monkeypatch.setattr(app_module, "registry_payload", original)

    rt = tmp_path / "stuart_rt" / "realtime_log"
    rows = _read_jsonl(rt / "events.jsonl")
    alerts = _read_jsonl(rt / "alerts.jsonl")

    assert any(r.get("event") == "api.error" for r in rows)
    assert any(r.get("event") == "alert.backend_exception" for r in alerts)
