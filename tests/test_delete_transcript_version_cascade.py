from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from ashby.modules.meetings.index import sqlite_fts
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.store import create_run, create_session
from ashby.modules.meetings.transcript_versions import create_transcript_version, list_transcript_versions


def _seed_index_for_run(stuart_root: Path, *, session_id: str, run_id: str, text: str) -> None:
    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=stuart_root))
    try:
        sqlite_fts.ensure_schema(conn)
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions(session_id, created_ts, mode, title) VALUES(?,?,?,?);",
                (session_id, 1.0, "meeting", "t"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?);",
                (run_id, session_id, 1.0, "succeeded"),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO segments(
                  session_id, run_id, segment_id, speaker_label, start_ms, end_ms, t_start, t_end, text, source_path
                ) VALUES(?,?,?,?,?,?,?,?,?,?);
                """,
                (session_id, run_id, 0, "SPEAKER_00", 0, 1000, 0.0, 1.0, text, "/tmp/t.json"),
            )
            conn.execute(
                "INSERT INTO segments_fts(text, session_id, run_id, segment_id, speaker_label, t_start, t_end, title, mode) VALUES(?,?,?,?,?,?,?,?,?);",
                (text, session_id, run_id, 0, "SPEAKER_00", 0.0, 1.0, "t", "meeting"),
            )
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_delete_transcript_version_requires_cascade_when_dependents_exist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    sid = create_session(mode="meeting", title="t")
    producer_run = create_run(session_id=sid, plan={"steps": [{"kind": "transcribe", "params": {"mode": "meeting"}}]})
    trv = create_transcript_version(
        sid,
        producer_run,
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "hello"}],
        diarization_enabled=False,
    )
    trv_id = str(trv["transcript_version_id"])
    consumer_run = create_run(
        session_id=sid,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "transcript_version_id": trv_id}}]},
    )

    _seed_index_for_run(init_stuart_root().root, session_id=sid, run_id=consumer_run, text="consumer text")
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await asyncio.wait_for(c.delete(f"/api/transcripts/{trv_id}"), timeout=10)
        body = r.json()
        assert r.status_code == 409
        assert body.get("error") == "TRANSCRIPT_HAS_DEPENDENTS"
        deps = body.get("dependents") or {}
        consumers = deps.get("consumers") or []
        assert any(str(row.get("run_id") or "") == consumer_run for row in consumers)
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_delete_transcript_version_cascade_deletes_dependents_and_hides_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    sid = create_session(mode="meeting", title="t")
    producer_run = create_run(session_id=sid, plan={"steps": [{"kind": "transcribe", "params": {"mode": "meeting"}}]})
    trv = create_transcript_version(
        sid,
        producer_run,
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "hello"}],
        diarization_enabled=False,
    )
    trv_id = str(trv["transcript_version_id"])
    consumer_run = create_run(
        session_id=sid,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "transcript_version_id": trv_id}}]},
    )
    lay = init_stuart_root()
    _seed_index_for_run(lay.root, session_id=sid, run_id=consumer_run, text="consumer text")

    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await asyncio.wait_for(c.delete(f"/api/transcripts/{trv_id}?cascade=true"), timeout=10)
        body = r.json()
        assert r.status_code == 200
        assert body.get("ok") is True
        assert body.get("deleted_transcript_version_id") == trv_id
        assert consumer_run in (body.get("deleted_runs") or [])
    finally:
        await c.aclose()

    assert not (lay.runs / consumer_run).exists()
    assert all(str(row.get("transcript_version_id") or "") != trv_id for row in list_transcript_versions(sid))

    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=lay.root))
    try:
        assert conn.execute("SELECT COUNT(*) FROM runs WHERE run_id = ?;", (consumer_run,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM segments WHERE run_id = ?;", (consumer_run,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM segments_fts WHERE run_id = ?;", (consumer_run,)).fetchone()[0] == 0
    finally:
        conn.close()
