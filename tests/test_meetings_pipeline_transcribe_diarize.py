from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.store import create_session, create_run, get_run_state, add_contribution
from ashby.modules.meetings.pipeline.job_runner import run_job


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


def test_formalize_creates_transcript_and_diarization_artifacts(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"kind": "formalize", "params": {}}]},
    )

    res = run_job(run_id)
    assert res.ok is True

    state = get_run_state(run_id)
    assert state["status"] == "succeeded"
    arts = state.get("artifacts") or []
    kinds = {a.get("kind") for a in arts}
    assert "transcript" in kinds
    assert "diarization" in kinds

    run_dir = root / "runs" / run_id
    tpath = run_dir / "artifacts" / "transcript.txt"
    dpath = run_dir / "artifacts" / "diarization.json"
    apath = run_dir / "artifacts" / "aligned_transcript.json"
    assert tpath.exists()
    assert dpath.exists()
    assert apath.exists()

    payload = json.loads(dpath.read_text(encoding="utf-8"))
    assert "segments" in payload
    assert "confidence" in payload
    assert "confidence_source" in payload
