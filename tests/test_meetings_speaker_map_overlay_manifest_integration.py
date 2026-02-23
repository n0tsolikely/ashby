from __future__ import annotations

import wave
from pathlib import Path

from ashby.modules.meetings.index import connect, get_db_path, ingest_run, list_sessions_by_attendee
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.overlays import create_speaker_map_overlay
from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.session_state import load_session_state, set_active_speaker_overlay
from ashby.modules.meetings.store import add_contribution, create_run, create_session, get_run_state


def _write_silence_wav(path: Path, *, seconds: float = 0.1, sr: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(seconds * sr)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * n_frames)


def test_run_records_speaker_map_overlay_artifact_and_sets_active(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    session_id = create_session(mode="meeting", title="Overlay Test")

    wav = tmp_path / "in.wav"
    _write_silence_wav(wav)
    add_contribution(session_id, wav, source_kind="audio")

    plan = {"steps": [{"kind": "speaker_map_overlay", "params": {"overlay": {"SPEAKER_00": "Greg"}}}]}
    run_id = create_run(session_id=session_id, plan=plan)

    res = run_job(run_id)
    assert res.ok is True

    state = get_run_state(run_id)
    arts = [a for a in (state.get("artifacts") or []) if isinstance(a, dict)]
    ovr = next((a for a in arts if a.get("kind") == "speaker_map_overlay"), None)
    assert ovr is not None

    # Artifact includes required overlay metadata (QUEST_068)
    assert isinstance(ovr.get("overlay_id"), str) and ovr.get("overlay_id")
    assert isinstance(ovr.get("sha256"), str) and ovr.get("sha256")
    assert isinstance(ovr.get("created_ts"), (int, float))
    assert isinstance(ovr.get("mapping"), dict)
    assert ovr["mapping"].get("SPEAKER_00") == "Greg"

    # Session state stores the active overlay pointer
    st = load_session_state(session_id)
    assert st.get("active_speaker_overlay_id") == ovr["overlay_id"]

    # Overlay artifact itself exists and is machine-readable
    overlay_path = Path(str(ovr.get("path")))
    assert overlay_path.exists()


def test_ingest_run_prefers_run_overlay_snapshot_over_session_state(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    session_id = create_session(mode="meeting", title="Overlay Snapshot")

    wav = tmp_path / "in.wav"
    _write_silence_wav(wav)
    add_contribution(session_id, wav, source_kind="audio")

    plan = {"steps": [{"kind": "speaker_map_overlay", "params": {"overlay": {"SPEAKER_00": "Greg"}}}]}
    run_id = create_run(session_id=session_id, plan=plan)

    res = run_job(run_id)
    assert res.ok is True

    lay = init_stuart_root()
    transcribe_stub(lay.runs / run_id)

    # First ingest uses the run's overlay snapshot
    ingest_run(run_id)

    # Change session-level active overlay AFTER the run
    ovr2 = create_speaker_map_overlay(session_id, {"SPEAKER_00": "Alice"})
    set_active_speaker_overlay(session_id, ovr2["overlay_id"])

    # Re-ingesting the same run must not drift to the new session overlay
    ingest_run(run_id)

    db_path = get_db_path(stuart_root=lay.root)
    conn = connect(db_path)
    try:
        got_greg = {s.session_id for s in list_sessions_by_attendee(conn, "greg")}
        got_alice = {s.session_id for s in list_sessions_by_attendee(conn, "alice")}
        assert session_id in got_greg
        assert session_id not in got_alice
    finally:
        conn.close()
