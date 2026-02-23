from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.store import add_contribution, create_run, create_session, get_run_state


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_transcribe_strict_mode_rejects_stub_engine(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    monkeypatch.setenv("ASHBY_ASR_STRICT", "1")
    monkeypatch.setenv("ASHBY_FAST_TESTS", "1")
    monkeypatch.delenv("ASHBY_ASR_ENABLE", raising=False)

    sid = create_session(mode="meeting", title="strict")
    src = tmp_path / "in.wav"
    src.write_bytes(b"fake")
    add_contribution(session_id=sid, source_path=src, source_kind="audio")

    run_id = create_run(
        session_id=sid,
        plan={"steps": [{"kind": "validate", "params": {}}, {"kind": "transcribe", "params": {"mode": "meeting"}}]},
    )
    res = run_job(run_id)
    assert res.ok is False
    assert res.status == "failed"
    assert "strict mode" in res.message.lower()
    assert "ASHBY_ASR_ENABLE=1" in res.message
    assert "faster-whisper" in res.message

    st = get_run_state(run_id)
    assert st.get("status") == "failed"


def test_transcript_integrity_report_blocks_invalid_segments(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    monkeypatch.delenv("ASHBY_ASR_STRICT", raising=False)

    sid = create_session(mode="meeting", title="integrity")
    src = tmp_path / "in.wav"
    src.write_bytes(b"fake")
    add_contribution(session_id=sid, source_path=src, source_kind="audio")

    def normalize(run_dir: Path, source_path: Path):
        out = run_dir / "artifacts" / "normalized.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(source_path.read_bytes())
        return {"kind": "normalized_audio", "path": str(out), "sha256": "x", "created_ts": 0}

    def transcribe_bad(run_dir: Path):
        txt = run_dir / "artifacts" / "transcript.txt"
        txt.write_text("bad\n", encoding="utf-8")
        payload = {
            "version": 1,
            "session_id": "",
            "run_id": run_dir.name,
            "engine": "faster-whisper",
            "segments": [{"segment_id": "A", "start_ms": 100, "end_ms": 10, "speaker": "SPEAKER_00", "text": "oops"}],
        }
        _write_json(run_dir / "artifacts" / "transcript.json", payload)
        return {"kind": "transcript", "path": str(txt), "json_path": str(run_dir / "artifacts" / "transcript.json"), "engine": "faster-whisper"}

    stub = SimpleNamespace(
        normalize=normalize,
        transcribe=transcribe_bad,
        diarize=lambda run_dir: {"kind": "diarization"},
        align=lambda run_dir: {"kind": "aligned_transcript"},
        pdf=lambda run_dir, **kwargs: {"kind": "pdf"},
    )
    monkeypatch.setattr("ashby.modules.meetings.pipeline.job_runner.get_meetings_adapter_matrix", lambda _profile: stub)

    run_id = create_run(
        session_id=sid,
        plan={
            "steps": [
                {"kind": "validate", "params": {}},
                {"kind": "transcribe", "params": {"mode": "journal", "diarization_enabled": False}},
            ]
        },
    )
    res = run_job(run_id)
    assert res.ok is False
    assert res.status == "failed"
    assert "integrity check failed" in res.message.lower()

    report_path = root / "runs" / run_id / "artifacts" / "transcript_integrity_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report.get("ok") is False
    issue_codes = {str(i.get("code") or "") for i in (report.get("issues") or []) if isinstance(i, dict)}
    assert "end_before_start" in issue_codes
