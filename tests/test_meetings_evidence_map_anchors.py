from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.store import create_session, add_contribution, create_run, get_run_state
from ashby.modules.meetings.pipeline.job_runner import run_job


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_evidence_map_has_real_anchors(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ff = shutil.which("ffmpeg")
    src = tmp_path / "src.wav"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(src)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    ses = create_session(mode="meeting", title="t")
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(session_id=ses, plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template": "default"}}]})
    res = run_job(run_id)
    assert res.ok is True

    st = get_run_state(run_id)
    arts = st.get("artifacts") or []
    ev = next((a for a in arts if a.get("kind") == "evidence_map"), None)
    assert ev is not None

    payload = json.loads(Path(ev["path"]).read_text(encoding="utf-8"))
    assert payload["version"] == 2
    claims = payload.get("claims") or []
    assert len(claims) >= 1

    # Find at least one claim with anchors (journal narrative sections can be uncited).
    anchors = None
    for c in claims:
        a = c.get("anchors") if isinstance(c, dict) else None
        if isinstance(a, list) and len(a) > 0:
            anchors = a
            break
    assert anchors is not None
    a0 = anchors[0]
    assert "segment_id" in a0
    assert "t_start" in a0
    assert "t_end" in a0
    assert "speaker_label" in a0
