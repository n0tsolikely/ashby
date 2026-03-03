from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from ashby.modules.meetings.index import connect, get_db_path, ingest_run, list_sessions_by_attendee
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.overlays import create_speaker_map_overlay
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.session_state import set_active_speaker_overlay, set_active_transcript_version
from ashby.modules.meetings.store import create_run, create_session
from ashby.modules.meetings.transcript_versions import create_transcript_version


def test_attendee_query_matches_only_user_provided_speaker_overlays(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    # Session A: has overlay mapping SPEAKER_00 -> Greg
    session_a = create_session(mode="meeting", title="A")
    run_a = create_run(session_id=session_a, plan={"steps": []})
    lay = init_stuart_root()
    transcribe_stub(lay.runs / run_a)

    ovr = create_speaker_map_overlay(session_a, {"SPEAKER_00": "Greg"})
    set_active_speaker_overlay(session_a, ovr["overlay_id"])
    ingest_run(run_a)

    # Session B: transcript mentions Greg but has NO overlay mapping.
    # Attendee query must NOT match this session (no false positives).
    session_b = create_session(mode="meeting", title="B")
    run_b = create_run(session_id=session_b, plan={"steps": []})
    lay2 = init_stuart_root()

    artifacts_dir = lay2.runs / run_b / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    dump_json(
        artifacts_dir / "transcript.json",
        {
            "version": 1,
            "session_id": session_b,
            "run_id": run_b,
            "segments": [
                {
                    "segment_id": 0,
                    "start_ms": 0,
                    "end_ms": 0,
                    "speaker": "SPEAKER_00",
                    "text": "Greg attended, but we did not set an overlay mapping.",
                }
            ],
        },
        write_once=True,
    )
    ingest_run(run_b)

    db_path = get_db_path(stuart_root=lay2.root)
    conn = connect(db_path)
    try:
        got = list_sessions_by_attendee(conn, "  gReG  ")
        got_ids = {s.session_id for s in got}
        assert session_a in got_ids
        assert session_b not in got_ids
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_api_sessions_attendee_filters_by_active_overlay_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    sid = create_session(mode="meeting", title="A")
    tv_old = create_transcript_version(
        session_id=sid,
        run_id="run_old",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "speaker": "SPEAKER_00", "text": "old"}],
        diarization_enabled=True,
    )["transcript_version_id"]
    tv_active = create_transcript_version(
        session_id=sid,
        run_id="run_active",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "speaker": "SPEAKER_00", "text": "new"}],
        diarization_enabled=True,
    )["transcript_version_id"]

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        # Historical mapping exists on an older transcript.
        put_old = await c.put(f"/api/transcripts/{tv_old}/speaker_map", json={"mapping": {"SPEAKER_00": "Greg"}})
        assert put_old.status_code == 200

        # Active transcript is different and has no mapping.
        set_active_transcript_version(sid, tv_active)

        no_match = await c.get("/api/sessions", params={"attendee": "greg"})
        assert no_match.status_code == 200
        no_rows = no_match.json().get("sessions") or []
        assert all(str(row.get("session_id") or "") != sid for row in no_rows)

        # Once active transcript gets the mapping, attendee filter should match.
        put_active = await c.put(f"/api/transcripts/{tv_active}/speaker_map", json={"mapping": {"SPEAKER_00": "Greg"}})
        assert put_active.status_code == 200
        yes_match = await c.get("/api/sessions", params={"attendee": "greg"})
        yes_rows = yes_match.json().get("sessions") or []
        yes_ids = {str(row.get("session_id") or "") for row in yes_rows}
        assert sid in yes_ids
    finally:
        await c.aclose()
