from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app


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
async def test_ui_event_writes_events_and_ui_sink(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_rt"))

    app = create_app()
    client = None
    await app.router.startup()
    try:
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
        payload = {
            "event": "ui.chat_send",
            "summary": "chat submit",
            "session_id": "ses_1",
            "run_id": None,
            "data": {"text_len": 5, "text_sha256": "abc"},
        }
        res = await client.post("/api/ui/event", json=payload, headers={"X-Correlation-Id": "cid-ui-1"})
        assert res.status_code == 200
    finally:
        if client is not None:
            await client.aclose()
        await app.router.shutdown()

    rt = tmp_path / "stuart_rt" / "realtime_log"
    events = _read_jsonl(rt / "events.jsonl")
    ui_rows = _read_jsonl(rt / "ui.jsonl")

    assert any(r.get("event") == "ui.chat_send" for r in events)
    assert any(r.get("event") == "ui.chat_send" for r in ui_rows)
    row = [r for r in ui_rows if r.get("event") == "ui.chat_send"][-1]
    assert row.get("correlation_id") == "cid-ui-1"


@pytest.mark.asyncio
async def test_ui_error_and_fetch_failed_emit_alerts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_rt"))

    app = create_app()
    client = None
    await app.router.startup()
    try:
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
        r1 = await client.post("/api/ui/event", json={"event": "ui.error", "summary": "boom", "data": {"message": "token=abc"}})
        r2 = await client.post("/api/ui/event", json={"event": "ui.fetch_failed", "summary": "route failed", "data": {"status": 500}})
        assert r1.status_code == 200
        assert r2.status_code == 200
    finally:
        if client is not None:
            await client.aclose()
        await app.router.shutdown()

    alerts = _read_jsonl(tmp_path / "stuart_rt" / "realtime_log" / "alerts.jsonl")
    assert any(r.get("event") == "alert.ui_error" for r in alerts)
    assert any(r.get("event") == "alert.ui_fetch_failed" for r in alerts)
