from pathlib import Path
import json

from ashby.modules.meetings.store import create_session, create_run, get_run_state
from ashby.modules.meetings.pipeline.job_runner import run_job


def test_formalize_creates_transcript_and_diarization_artifacts(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")
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
    assert "diarization_segments" in kinds

    run_dir = root / "runs" / run_id
    tpath = run_dir / "artifacts" / "transcript.txt"
    dpath = run_dir / "artifacts" / "diarization_segments.json"
    assert tpath.exists()
    assert dpath.exists()

    payload = json.loads(dpath.read_text(encoding="utf-8"))
    assert "segments" in payload
