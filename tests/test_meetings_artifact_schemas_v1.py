from __future__ import annotations

from pathlib import Path

import pytest

from ashby.modules.meetings.schemas.artifacts_v1 import (
    dump_json,
    validate_diarization_v1,
    validate_transcript_v1,
    validate_transcript_version_v1,
)


def test_dump_json_write_once(tmp_path: Path):
    p = tmp_path / "x.json"
    dump_json(p, {"a": 1}, write_once=True)
    assert p.exists()
    with pytest.raises(FileExistsError):
        dump_json(p, {"a": 2}, write_once=True)


def test_validate_transcript_v1_minimal():
    payload = {"version": 1, "session_id": "ses_x", "run_id": "run_x", "segments": []}
    validate_transcript_v1(payload)


def test_validate_transcript_version_v1_minimal():
    payload = {
        "version": 1,
        "transcript_version_id": "trv_abc",
        "session_id": "ses_x",
        "run_id": "run_x",
        "created_ts": 1.23,
        "diarization_enabled": False,
        "asr_engine": "default",
        "audio_ref": {},
        "segments": [{"segment_id": 0, "start_ms": 0, "end_ms": 10, "text": "hello"}],
    }
    validate_transcript_version_v1(payload)


def test_validate_diarization_v1_minimal():
    payload = {"version": 1, "session_id": "ses_x", "run_id": "run_x", "segments": []}
    validate_diarization_v1(payload)
