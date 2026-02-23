from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ashby.modules.meetings.adapters.diarize_pyannote import diarize_pyannote
from ashby.modules.meetings.pipeline.align import align_transcript_time_overlap


class _Turn:
    def __init__(self, start: float, end: float):
        self.start = start
        self.end = end


class _FakeDiar:
    def __init__(self, segments: List[Dict[str, Any]]):
        self._segments = segments

    def itertracks(self, *, yield_label: bool = True):
        for s in self._segments:
            yield None, _Turn(s["start"], s["end"]), s["speaker"]


def _write_minimal_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "sessions" / "ses_test" / "runs" / "run_test"
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    # normalized.wav is required by diarize_pyannote
    (run_dir / "artifacts" / "normalized.wav").write_bytes(b"RIFF0000WAVE")

    transcript = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "engine": "stub_asr",
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "a"},
            {"segment_id": 1, "start_ms": 1000, "end_ms": 2000, "speaker": "SPEAKER_00", "text": "b"},
        ],
    }
    (run_dir / "artifacts" / "transcript.json").write_text(
        json.dumps(transcript, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return run_dir


def _install_fake_pyannote(monkeypatch: pytest.MonkeyPatch, pipeline_cls: Any) -> None:
    mod_audio = types.ModuleType("pyannote.audio")
    mod_audio.Pipeline = pipeline_cls
    pkg = types.ModuleType("pyannote")
    pkg.audio = mod_audio

    monkeypatch.setitem(sys.modules, "pyannote", pkg)
    monkeypatch.setitem(sys.modules, "pyannote.audio", mod_audio)


def test_diarize_pyannote_uses_token_kwarg_when_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: List[Dict[str, Any]] = []

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, model: str, **kwargs):
            calls.append(dict(kwargs))
            assert "token" in kwargs  # should use new API
            assert "use_auth_token" not in kwargs
            return cls()

        def __call__(self, wav_path: str, **kwargs):
            return _FakeDiar(
                [
                    {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
                    {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
                ]
            )

    _install_fake_pyannote(monkeypatch, FakePipeline)
    monkeypatch.setenv("HF_TOKEN", "tok")

    run_dir = _write_minimal_run(tmp_path)
    diar_art = diarize_pyannote(run_dir)

    d = json.loads((run_dir / "artifacts" / "diarization.json").read_text(encoding="utf-8"))
    assert d.get("engine") == "pyannote"
    assert d.get("pyannote_auth_arg") == "token"
    assert len(d.get("segments") or []) >= 2

    # alignment should now show >1 speaker label
    align_transcript_time_overlap(run_dir)
    aligned = json.loads((run_dir / "artifacts" / "aligned_transcript.json").read_text(encoding="utf-8"))
    speakers = {s.get("speaker") for s in aligned.get("segments") or []}
    assert "SPEAKER_00" in speakers
    assert "SPEAKER_01" in speakers

    assert calls and "token" in calls[0]


def test_diarize_pyannote_falls_back_to_use_auth_token_for_old_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: List[Dict[str, Any]] = []

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, model: str, **kwargs):
            calls.append(dict(kwargs))
            # Simulate old API: token kwarg not accepted.
            if "token" in kwargs:
                raise TypeError("unexpected keyword argument 'token'")
            assert "use_auth_token" in kwargs
            return cls()

        def __call__(self, wav_path: str, **kwargs):
            return _FakeDiar(
                [
                    {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
                    {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
                ]
            )

    _install_fake_pyannote(monkeypatch, FakePipeline)
    monkeypatch.setenv("HF_TOKEN", "tok")

    run_dir = _write_minimal_run(tmp_path)
    diarize_pyannote(run_dir)

    d = json.loads((run_dir / "artifacts" / "diarization.json").read_text(encoding="utf-8"))
    assert d.get("engine") == "pyannote"
    assert d.get("pyannote_auth_arg") == "use_auth_token"

    # call order should be: try token, then fallback to use_auth_token
    assert len(calls) == 2
    assert "token" in calls[0]
    assert "use_auth_token" in calls[1]
