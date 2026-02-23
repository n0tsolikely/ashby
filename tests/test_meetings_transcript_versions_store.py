from __future__ import annotations

from pathlib import Path

import pytest

from ashby.modules.meetings.store import create_session
from ashby.modules.meetings.transcript_versions import (
    create_transcript_version,
    ensure_transcripts_dirs,
    list_transcript_versions,
    load_transcript_version,
    resolve_transcript_version,
)


def test_transcript_version_create_list_load_resolve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    session_id = create_session(mode="meeting", title="tv")
    ensure_transcripts_dirs(session_id)

    payload = create_transcript_version(
        session_id=session_id,
        run_id="run_abc",
        diarization_enabled=True,
        asr_engine="default",
        audio_ref={"path": f"sessions/{session_id}/audio/source.wav", "kind": "normalized_audio"},
        segments=[
            {
                "segment_id": 1,
                "start_ms": 0,
                "end_ms": 1500,
                "speaker": "SPEAKER_00",
                "text": "hello",
                "confidence": 0.91,
            }
        ],
    )

    tv_id = payload["transcript_version_id"]
    assert tv_id.startswith("trv_")

    versions = list_transcript_versions(session_id)
    assert len(versions) == 1
    assert versions[0]["transcript_version_id"] == tv_id
    assert versions[0]["run_id"] == "run_abc"
    assert versions[0]["segments_count"] == 1

    loaded = load_transcript_version(session_id, tv_id)
    assert loaded["session_id"] == session_id
    assert loaded["audio_ref"]["path"].startswith(f"sessions/{session_id}/")
    assert loaded["segments"][0]["text"] == "hello"

    resolved = resolve_transcript_version(tv_id)
    assert resolved is not None
    assert resolved["session_id"] == session_id
    assert resolved["run_id"] == "run_abc"

    version_file = root / "sessions" / session_id / "transcripts" / "versions" / f"{tv_id}.json"
    assert version_file.exists()
    assert (root / "sessions" / session_id / "transcripts" / "index.jsonl").exists()
    assert (root / "transcript_versions" / "lookup.jsonl").exists()


def test_transcript_version_rejects_audio_ref_absolute_outside_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    session_id = create_session(mode="meeting", title="tv")

    with pytest.raises(ValueError, match="audio_ref.path absolute path must stay under STUART_ROOT"):
        create_transcript_version(
            session_id=session_id,
            run_id="run_abc",
            diarization_enabled=False,
            audio_ref={"path": "/etc/passwd"},
            segments=[{"segment_id": 1, "start_ms": 0, "end_ms": 1, "text": "x"}],
        )
