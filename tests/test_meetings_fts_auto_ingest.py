from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.store import create_session, add_contribution, create_run, get_run_state
from ashby.modules.meetings.pipeline.job_runner import run_job


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_formalize_auto_triggers_fts_ingest(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    # generate valid wav
    src = tmp_path / "src.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(src)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    ses = create_session(mode="meeting", title="t")
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(session_id=ses, plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template": "default"}}]})
    res = run_job(run_id)
    assert res.ok is True

    st = get_run_state(run_id)
    arts = st.get("artifacts") or []
    fi = next((a for a in arts if a.get("kind") == "fts_ingest"), None)
    assert fi is not None

    receipt_path = Path(fi["path"])
    assert receipt_path.exists()
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload.get("version") == 1
    assert payload.get("run_id") == run_id
