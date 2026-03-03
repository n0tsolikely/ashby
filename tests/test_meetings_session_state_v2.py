from __future__ import annotations

from pathlib import Path

from ashby.modules.meetings.session_state import (
    get_speaker_overlay_for_transcript,
    load_session_state,
    seed_speaker_overlay_for_new_transcript,
    set_active_speaker_overlay,
    set_active_transcript_version,
    set_speaker_overlay_for_transcript,
)
from ashby.modules.meetings.store import create_session
from ashby.modules.meetings.transcript_versions import create_transcript_version


def test_overlay_map_tracks_active_transcript_and_legacy_pointer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    sid = create_session(mode="meeting", title="state_v2")

    tv1 = create_transcript_version(
        session_id=sid,
        run_id="run_1",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "text": "a"}],
        diarization_enabled=False,
    )["transcript_version_id"]
    tv2 = create_transcript_version(
        session_id=sid,
        run_id="run_2",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "text": "b"}],
        diarization_enabled=False,
    )["transcript_version_id"]

    set_active_transcript_version(sid, tv1)
    set_active_speaker_overlay(sid, "ovr_a")
    assert get_speaker_overlay_for_transcript(sid, tv1) == "ovr_a"

    # Switching active transcript derives legacy pointer from transcript-scoped overlay.
    set_active_transcript_version(sid, tv2)
    st = load_session_state(sid)
    assert st.get("active_speaker_overlay_id") is None

    set_active_speaker_overlay(sid, "ovr_b")
    assert get_speaker_overlay_for_transcript(sid, tv2) == "ovr_b"

    set_active_transcript_version(sid, tv1)
    st2 = load_session_state(sid)
    assert st2.get("active_speaker_overlay_id") == "ovr_a"


def test_seed_forward_and_transcript_scoped_setter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    sid = create_session(mode="meeting", title="state_v2_seed")

    tv1 = create_transcript_version(
        session_id=sid,
        run_id="run_src",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "text": "src"}],
        diarization_enabled=False,
    )["transcript_version_id"]
    set_active_transcript_version(sid, tv1)
    set_active_speaker_overlay(sid, "ovr_seed")

    tv2 = create_transcript_version(
        session_id=sid,
        run_id="run_new",
        segments=[{"segment_id": 0, "start_ms": 0, "end_ms": 10, "text": "new"}],
        diarization_enabled=False,
    )["transcript_version_id"]
    seed_speaker_overlay_for_new_transcript(sid, tv2)
    assert get_speaker_overlay_for_transcript(sid, tv2) == "ovr_seed"

    set_speaker_overlay_for_transcript(sid, tv2, "ovr_custom")
    set_active_transcript_version(sid, tv2)
    st = load_session_state(sid)
    assert st.get("active_speaker_overlay_id") == "ovr_custom"
