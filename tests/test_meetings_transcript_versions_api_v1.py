from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.session_state import load_session_state
from ashby.modules.meetings.store import create_run, create_session, get_run_state
from ashby.modules.meetings.transcript_versions import create_transcript_version


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_transcripts_list_metadata_only_and_active_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    sid = create_session(mode="meeting", title="t")
    tv1 = create_transcript_version(
        session_id=sid,
        run_id="run_a",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "text": "hello"}],
        diarization_enabled=False,
        asr_engine="default",
    )["transcript_version_id"]
    tv2 = create_transcript_version(
        session_id=sid,
        run_id="run_b",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "speaker": "SPEAKER_00", "text": "hi"}],
        diarization_enabled=True,
        asr_engine="stub",
    )["transcript_version_id"]

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.patch(f"/api/sessions/{sid}/transcripts/active", json={"transcript_version_id": tv2})
        assert r.status_code == 200
        r2 = await c.get(f"/api/sessions/{sid}/transcripts")
    finally:
        await c.aclose()

    data = r2.json()
    rows = data["transcripts"]
    assert len(rows) >= 2
    ids = {row["transcript_version_id"] for row in rows}
    assert tv1 in ids and tv2 in ids
    for row in rows:
        assert "segments_count" in row
        assert "diarization_enabled" in row
        assert "asr_engine" in row
        assert "active" in row
        assert "transcript_json" not in row
    active_rows = [row for row in rows if row["active"]]
    assert len(active_rows) == 1
    assert active_rows[0]["transcript_version_id"] == tv2


@pytest.mark.asyncio
async def test_transcript_get_by_trv_and_404(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    sid = create_session(mode="meeting", title="t")
    tv = create_transcript_version(
        session_id=sid,
        run_id="run_get",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "speaker": "SPEAKER_01", "text": "hello world"}],
        diarization_enabled=True,
        asr_engine="default",
        audio_ref={"contribution_id": "con_1"},
    )["transcript_version_id"]

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.get(f"/api/transcripts/{tv}")
        assert r.status_code == 200
        t = r.json()["transcript"]
        assert t["transcript_version_id"] == tv
        assert t["session_id"] == sid
        assert t["diarization_enabled"] is True
        assert isinstance(t["segments"], list) and len(t["segments"]) == 1

        r404 = await c.get("/api/transcripts/trv_does_not_exist")
        assert r404.status_code == 404
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_legacy_tv_run_id_resolution_backfills_versions(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    root = tmp_path / "stuart_runtime"
    sid = create_session(mode="meeting", title="t")
    rid = "run_legacy_1"
    _write_json(root / "runs" / rid / "run.json", {"run_id": rid, "session_id": sid, "created_ts": 1.0, "plan": {}, "status": "succeeded"})
    _write_json(
        root / "runs" / rid / "artifacts" / "transcript.json",
        {
            "version": 1,
            "session_id": sid,
            "run_id": rid,
            "segments": [{"segment_id": 0, "start_ms": 0, "end_ms": 10, "text": "legacy"}],
        },
    )

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.get(f"/api/transcripts/tv__{rid}")
        assert r.status_code == 200
        t = r.json()["transcript"]
        assert t["session_id"] == sid
        assert t["run_id"] == rid
        assert str(t["transcript_version_id"]).startswith("trv_")
    finally:
        await c.aclose()


def test_formalize_consumes_transcript_version_without_heavy_stages(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    sid = create_session(mode="meeting", title="t")
    tv = create_transcript_version(
        session_id=sid,
        run_id="run_source",
        segments=[
            {"segment_id": 0, "start_ms": 0, "end_ms": 10, "speaker": "SPEAKER_00", "text": "decision one"},
            {"segment_id": 1, "start_ms": 11, "end_ms": 20, "speaker": "SPEAKER_01", "text": "action two"},
        ],
        diarization_enabled=True,
        asr_engine="default",
    )["transcript_version_id"]

    run_id = create_run(
        session_id=sid,
        plan={
            "steps": [
                {"kind": "validate", "params": {}},
                {
                    "kind": "formalize",
                    "params": {
                        "mode": "meeting",
                        "template_id": "default",
                        "retention": "MED",
                        "transcript_version_id": tv,
                    },
                },
            ]
        },
    )
    result = run_job(run_id)
    assert result.ok is True

    st = get_run_state(run_id)
    assert st.get("status") == "succeeded"
    artifacts = [a for a in (st.get("artifacts") or []) if isinstance(a, dict)]
    kinds = {a.get("kind") for a in artifacts}
    assert "normalize_skipped" in kinds
    assert "transcript_from_version" in kinds
    assert "consumed_transcript_version" in kinds
    assert "transcript" not in kinds
    po = st.get("primary_outputs") or {}
    assert po.get("consumed_transcript_version_id") == tv

    minutes_json = Path(tmp_path / "stuart_runtime" / "runs" / run_id / "artifacts" / "minutes.json")
    payload = json.loads(minutes_json.read_text(encoding="utf-8"))
    assert payload.get("transcript_version_id") == tv

    ss = load_session_state(sid)
    assert ss.get("active_transcript_version_id") is not None
