from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.store import create_session, add_contribution, create_run, get_run_state
from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.init_root import init_stuart_root


def _gen_wav(path: Path) -> None:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not installed")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def test_journal_mode_skips_diarization(tmp_path: Path, monkeypatch):
    # Journal should default skip diarization (single speaker)
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    ses = create_session(mode="journal", title="j")
    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(session_id=ses, plan={"steps": [{"kind": "formalize", "params": {"mode": "journal", "template": "default"}}]})
    res = run_job(run_id)
    assert res.ok is True

    st = get_run_state(run_id)
    kinds = {a.get("kind") for a in (st.get("artifacts") or [])}
    assert "diarization" not in kinds

    run_dir = init_stuart_root().runs / run_id
    assert not (run_dir / "artifacts" / "diarization.json").exists()


def test_meeting_mode_writes_speaker_hint_and_payload_field(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    ses = create_session(mode="meeting", title="m")
    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(session_id=ses, plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template": "default", "speakers": 2}}]})
    res = run_job(run_id)
    assert res.ok is True

    run_dir = init_stuart_root().runs / run_id
    hint_path = run_dir / "inputs" / "speaker_hint.json"
    assert hint_path.exists()
    hint = json.loads(hint_path.read_text(encoding="utf-8"))
    assert hint.get("speakers") == 2

    dpath = run_dir / "artifacts" / "diarization.json"
    assert dpath.exists()
    payload = json.loads(dpath.read_text(encoding="utf-8"))
    assert payload.get("version") == 1
    assert payload.get("speaker_hint") == 2
    assert "confidence" in payload
    assert "confidence_source" in payload
    if payload.get("segments"):
        assert "confidence" in payload["segments"][0]
