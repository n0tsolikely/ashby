from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.router.router import build_intent_and_plan
from ashby.modules.meetings.schemas.plan import SessionContext
from ashby.modules.meetings.schemas.run_request import RunRequest
from ashby.modules.meetings.store import create_session, create_run, get_run_state, add_contribution
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.index import ingest_run
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


def test_search_plan_step_executes_and_returns_citations(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="A")

    # Seed at least one contribution (normalize requires valid audio now)
    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    # Seed: a session with an indexed transcript.
    run_seed = create_run(session_id=ses, plan={"steps": []})
    lay = init_stuart_root()
    transcribe_stub(lay.runs / run_seed)
    ingest_run(run_seed)

    out = build_intent_and_plan(
        text="search kimchi",
        run_request=RunRequest(mode="meeting"),
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
    assert payload["query"] == "kimchi"
    assert payload["total_hits"] >= 1

    # QUEST_058: payload must record filters used so doors can display scope.
    assert payload.get("session_filter") == ses
    assert payload.get("mode_filter") == "meeting"

    top = payload["results"][0]
    assert "snippet" in top
    assert "citation" in top

    cite = top["citation"]
    assert cite["session_id"] == ses
    assert isinstance(cite["run_id"], str) and cite["run_id"].startswith("run_")
    assert isinstance(cite["segment_id"], int)
    # Timestamps exist as keys (may be null in stub transcripts).
    assert "t_start" in cite
    assert "t_end" in cite


def test_search_no_hits_returns_clear_message(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="A")

    # Seed at least one contribution
    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_seed = create_run(session_id=ses, plan={"steps": []})
    lay = init_stuart_root()
    transcribe_stub(lay.runs / run_seed)
    ingest_run(run_seed)

    out = build_intent_and_plan(
        text="search definitelynotaword_zzz",
        run_request=RunRequest(mode="meeting"),
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
    assert payload.get("session_filter") == ses
    assert payload.get("mode_filter") == "meeting"
