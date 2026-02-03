import json

from ashby.modules.meetings.router.router import build_intent_and_plan
from ashby.modules.meetings.schemas.plan import UIState, SessionContext
from ashby.modules.meetings.store import create_session, create_run, get_run_state
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.index import ingest_run
from ashby.modules.meetings.pipeline.job_runner import run_job


def test_search_plan_step_executes_and_returns_citations(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    # Seed: a session with an indexed transcript.
    ses = create_session(mode="meeting", title="A")
    run_seed = create_run(session_id=ses, plan={"steps": []})
    lay = init_stuart_root()
    transcribe_stub(lay.runs / run_seed)
    ingest_run(run_seed)

    # Build search plan from the router.
    out = build_intent_and_plan(
        text="search kimchi",
        ui=UIState(mode="meeting"),
        session=SessionContext(active_session_id=ses),
    )

    # Execute the plan as a run (validate step is allowed as no-op).
    steps = [{"kind": s.kind.value, "params": dict(s.params)} for s in out.plan.steps]
    run_search = create_run(session_id=ses, plan={"steps": steps})

    res = run_job(run_search)
    assert res.ok is True

    st = get_run_state(run_search)
    arts = st.get("artifacts") or []
    sr = next((a for a in arts if a.get("kind") == "search_results"), None)
    assert sr is not None, "Expected search_results artifact"

    payload = json.loads(open(sr["path"], "r", encoding="utf-8").read())
    assert payload["query"] == "kimchi"
    assert payload["total_hits"] >= 1

    top = payload["results"][0]
    assert "snippet" in top
    assert "citation" in top

    cite = top["citation"]
    assert cite["session_id"] == ses
    assert isinstance(cite["run_id"], str) and cite["run_id"].startswith("run_")
    assert isinstance(cite["segment_id"], int)


def test_search_no_hits_returns_clear_message(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="A")
    run_seed = create_run(session_id=ses, plan={"steps": []})
    lay = init_stuart_root()
    transcribe_stub(lay.runs / run_seed)
    ingest_run(run_seed)

    out = build_intent_and_plan(
        text="search definitelynotaword_zzz",
        ui=UIState(mode="meeting"),
        session=SessionContext(active_session_id=ses),
    )

    steps = [{"kind": s.kind.value, "params": dict(s.params)} for s in out.plan.steps]
    run_search = create_run(session_id=ses, plan={"steps": steps})

    res = run_job(run_search)
    assert res.ok is True

    st = get_run_state(run_search)
    arts = st.get("artifacts") or []
    sr = next((a for a in arts if a.get("kind") == "search_results"), None)
    assert sr is not None

    payload = json.loads(open(sr["path"], "r", encoding="utf-8").read())
    assert payload["total_hits"] == 0
    assert payload.get("message") and "No hits" in payload["message"]
