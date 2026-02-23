from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.store import create_session, add_contribution, create_run, get_run_state
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


def test_formalize_triggers_fts_ingest(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")
    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(session_id=ses, plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template": "default"}}]})
    res = run_job(run_id)
    assert res.ok is True

    st = get_run_state(run_id)
    arts = st.get("artifacts") or []
    fi = next((a for a in arts if a.get("kind") == "fts_ingest"), None)
    assert fi is not None
