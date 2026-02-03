from pathlib import Path

from ashby.modules.meetings.store import create_session, create_run, get_run_state


def test_create_run_initializes_queued_and_writes_event(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    session_id = create_session(mode="meeting", title="t")
    run_id = create_run(session_id=session_id, plan={"steps": []})

    state = get_run_state(run_id)
    assert state["run_id"] == run_id
    assert state["session_id"] == session_id
    assert state["status"] == "queued"
    assert state["stage"] == "queued"
    assert state["progress"] == 0

    events = root / "runs" / run_id / "events.jsonl"
    assert events.exists()
    lines = events.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
