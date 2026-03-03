from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from ashby.modules.meetings.store import create_run, create_session
from ashby.modules.meetings.transcript_versions import create_transcript_version


@pytest.mark.asyncio
async def test_sessions_q_matches_run_id_and_transcript_version_id(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    sid = create_session(mode="meeting", title="Session Search API")
    run_id = create_run(session_id=sid, plan={"steps": []})
    tv = create_transcript_version(
        session_id=sid,
        run_id=run_id,
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "text": "hello"}],
        diarization_enabled=False,
    )["transcript_version_id"]

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        q_run = run_id[-8:]
        resp_run = await c.get("/api/sessions", params={"q": q_run})
        assert resp_run.status_code == 200
        rows_run = resp_run.json().get("sessions") or []
        by_id_run = {str(r.get("session_id") or ""): r for r in rows_run}
        assert sid in by_id_run
        assert "ID_MATCH" in (by_id_run[sid].get("match_kinds") or [])

        q_tv = tv[-8:]
        resp_tv = await c.get("/api/sessions", params={"q": q_tv})
        assert resp_tv.status_code == 200
        rows_tv = resp_tv.json().get("sessions") or []
        by_id_tv = {str(r.get("session_id") or ""): r for r in rows_tv}
        assert sid in by_id_tv
        assert "ID_MATCH" in (by_id_tv[sid].get("match_kinds") or [])
    finally:
        await c.aclose()
