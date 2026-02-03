from pathlib import Path

from ashby.modules.meetings.store import create_session, create_run, get_run_state
from ashby.modules.meetings.pipeline.job_runner import run_job, poll_progress


def test_job_runner_transitions_and_progress(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")
    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"name": "stage0_ingest"}, {"name": "stage1_normalize"}]},
    )

    # initial state
    s0 = get_run_state(run_id)
    assert s0["status"] == "queued"
    assert s0["progress"] == 0
    assert (root / "runs" / run_id / "events.jsonl").exists()

    res = run_job(run_id)
    assert res.ok is True
    assert res.status == "succeeded"

    s1 = get_run_state(run_id)
    assert s1["status"] == "succeeded"
    assert s1["progress"] == 100
    assert s1["started_ts"] is not None
    assert s1["ended_ts"] is not None

    p = poll_progress(run_id)
    assert p["status"] == "succeeded"
    assert p["progress"] == 100

    events = root / "runs" / run_id / "events.jsonl"
    lines = events.read_text(encoding="utf-8").strip().splitlines()
    # queued + running + step(s) + succeeded (>= 4)
    assert len(lines) >= 4


def test_job_runner_empty_steps_still_succeeds(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")
    run_id = create_run(session_id=ses, plan={"steps": []})

    res = run_job(run_id)
    assert res.ok is True

    s = get_run_state(run_id)
    assert s["status"] == "succeeded"
    assert s["progress"] == 100
