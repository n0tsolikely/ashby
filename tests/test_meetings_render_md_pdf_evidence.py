from pathlib import Path
import json

from ashby.modules.meetings.store import create_session, create_run, get_run_state
from ashby.modules.meetings.pipeline.job_runner import run_job


def test_formalize_renders_md_evidence_and_pdf(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")
    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template": "default"}}]},
    )

    res = run_job(run_id)
    assert res.ok is True

    state = get_run_state(run_id)
    assert state["status"] == "succeeded"

    arts = state.get("artifacts") or []
    kinds = {a.get("kind") for a in arts}
    assert "transcript" in kinds
    assert "diarization_segments" in kinds
    assert "formalized_md" in kinds
    assert "evidence_map" in kinds
    assert "formalized_pdf" in kinds

    run_dir = root / "runs" / run_id
    md_path = run_dir / "artifacts" / "formalized.md"
    ev_path = run_dir / "artifacts" / "evidence_map.json"
    pdf_path = run_dir / "exports" / "formalized.pdf"

    assert md_path.exists()
    assert ev_path.exists()
    assert pdf_path.exists()

    payload = json.loads(ev_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert "claims" in payload
