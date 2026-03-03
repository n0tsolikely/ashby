from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from ashby.modules.meetings.store import create_run, create_session
from ashby.modules.meetings.init_root import init_stuart_root


@pytest.mark.asyncio
async def test_web_delete_run_and_session_endpoints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    sid = create_session(mode="meeting", title="delete test")
    run_id = create_run(session_id=sid, plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting"}}]})
    lay = init_stuart_root()
    assert (lay.runs / run_id).exists()
    assert (lay.sessions / sid).exists()

    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        del_run = await asyncio.wait_for(c.delete(f"/api/runs/{run_id}"), timeout=10)
        body_run = del_run.json()
        assert del_run.status_code == 200
        assert body_run.get("ok") is True
        assert not (lay.runs / run_id).exists()

        del_session = await asyncio.wait_for(c.delete(f"/api/sessions/{sid}"), timeout=10)
        body_sess = del_session.json()
        assert del_session.status_code == 200
        assert body_sess.get("ok") is True
        assert not (lay.sessions / sid).exists()
    finally:
        await c.aclose()
