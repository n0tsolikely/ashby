from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.overlays import create_speaker_map_overlay
from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.session_state import set_active_speaker_overlay
from ashby.modules.meetings.store import add_contribution, create_run, create_session, get_run_state


def _as_jsonable(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, Path):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def cmd_upload(args: argparse.Namespace) -> Dict[str, Any]:
    session_id = args.session_id or create_session(mode=args.mode, title=args.title)
    p = Path(args.path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    contribution_id = add_contribution(session_id=session_id, source_path=p, source_kind=args.kind)
    return {"ok": True, "session_id": session_id, "contribution_id": contribution_id}


def _make_run(session_id: str, plan: Dict[str, Any], *, auto_go: bool) -> Dict[str, Any]:
    run_id = create_run(session_id=session_id, plan=plan)
    if auto_go:
        run_job(run_id)
    state = get_run_state(run_id)
    return {"ok": True, "run_id": run_id, "status": state.get("status"), "state": _as_jsonable(state)}


def cmd_plan(args: argparse.Namespace) -> Dict[str, Any]:
    plan = {"steps": [{"kind": "formalize", "params": {"mode": args.mode, "template": args.template}}]}
    out = _make_run(args.session_id, plan, auto_go=False)
    out["status"] = "pending_go"
    return out


def cmd_go(args: argparse.Namespace) -> Dict[str, Any]:
    run_job(args.run_id)
    state = get_run_state(args.run_id)
    return {"ok": True, "run_id": args.run_id, "status": state.get("status"), "state": _as_jsonable(state)}


def cmd_run(args: argparse.Namespace) -> Dict[str, Any]:
    plan = {"steps": [{"kind": "formalize", "params": {"mode": args.mode, "template": args.template}}]}
    return _make_run(args.session_id, plan, auto_go=True)


def cmd_status(args: argparse.Namespace) -> Dict[str, Any]:
    state = get_run_state(args.run_id)
    return {"ok": True, "state": _as_jsonable(state)}


def cmd_overlay_set(args: argparse.Namespace) -> Dict[str, Any]:
    stmt = (args.mapping or "").strip()
    if " is " not in stmt.lower():
        raise ValueError("Expected format: 'SPEAKER_00 is Greg'")
    left, right = stmt.split("is", 1)
    label = left.strip().upper()
    name = right.strip()
    if not label.startswith("SPEAKER_"):
        raise ValueError("Left side must be SPEAKER_XX")
    if not name:
        raise ValueError("Name is empty")

    ovr = create_speaker_map_overlay(args.session_id, {label: name})
    st = set_active_speaker_overlay(args.session_id, ovr["overlay_id"])
    return {"ok": True, "session_id": args.session_id, "overlay": ovr, "session_state": st}


def cmd_rerender(args: argparse.Namespace) -> Dict[str, Any]:
    plan = {
        "steps": [
            {
                "kind": "formalize",
                "params": {"mode": args.mode, "template": args.template, "reuse_run_id": args.source_run_id},
            }
        ]
    }
    return _make_run(args.session_id, plan, auto_go=True)


def cmd_extract(args: argparse.Namespace) -> Dict[str, Any]:
    plan = {"steps": [{"kind": "extract_only", "params": {"query": args.who}}]}
    return _make_run(args.session_id, plan, auto_go=True)


def cmd_search(args: argparse.Namespace) -> Dict[str, Any]:
    plan = {"steps": [{"kind": "search", "params": {"query": args.query, "session_id": args.session_id, "limit": args.limit}}]}
    return _make_run(args.session_id, plan, auto_go=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stuart", description="Stuart v1 (meetings module) CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload", help="Upload audio/video into Stuart runtime (no processing).")
    up.add_argument("path", help="Path to audio/video file")
    up.add_argument("--kind", choices=["audio", "video"], required=True, help="Source kind")
    up.add_argument("--mode", choices=["meeting", "journal"], default="meeting")
    up.add_argument("--title", default=None)
    up.add_argument("--session-id", dest="session_id", default=None)
    up.set_defaults(_handler=cmd_upload)

    pl = sub.add_parser("plan", help="Create a run only (no processing).")
    pl.add_argument("session_id", help="Existing session id (ses_...)")
    pl.add_argument("--mode", choices=["meeting", "journal"], default="meeting")
    pl.add_argument("--template", default="default")
    pl.set_defaults(_handler=cmd_plan)

    go = sub.add_parser("go", help="Execute an existing run_id.")
    go.add_argument("run_id", help="Run ID (run_...)")
    go.set_defaults(_handler=cmd_go)

    rn = sub.add_parser("run", help="Create a run and execute processing for a session.")
    rn.add_argument("session_id", help="Existing session id (ses_...)")
    rn.add_argument("--mode", choices=["meeting", "journal"], default="meeting")
    rn.add_argument("--template", default="default")
    rn.set_defaults(_handler=cmd_run)

    st = sub.add_parser("status", help="Show run state.")
    st.add_argument("run_id", help="Run id (run_...)")
    st.set_defaults(_handler=cmd_status)

    ov = sub.add_parser("overlay-set", help="Set a speaker mapping overlay (append-only) and activate it.")
    ov.add_argument("session_id", help="Session id (ses_...)")
    ov.add_argument("mapping", help='Mapping statement, e.g. "SPEAKER_00 is Greg"')
    ov.set_defaults(_handler=cmd_overlay_set)

    rr = sub.add_parser("rerender", help="Rerender outputs using active overlay, reusing a prior transcript.")
    rr.add_argument("session_id", help="Session id (ses_...)")
    rr.add_argument("source_run_id", help="Existing run_id to reuse transcript from")
    rr.add_argument("--mode", choices=["meeting", "journal"], default="meeting")
    rr.add_argument("--template", default="default")
    rr.set_defaults(_handler=cmd_rerender)

    ex = sub.add_parser("extract", help="Export only what a named speaker said (requires active mapping).")
    ex.add_argument("session_id", help="Session id (ses_...)")
    ex.add_argument("who", help="Speaker name (must match active overlay mapping)")
    ex.set_defaults(_handler=cmd_extract)

    sr = sub.add_parser("search", help="Search transcripts via SQLite FTS (returns citation-aware results).")
    sr.add_argument("session_id", help="Session id (ses_...)")
    sr.add_argument("query", help="Search query text")
    sr.add_argument("--limit", type=int, default=10)
    sr.set_defaults(_handler=cmd_search)


    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "_handler", None)
    if handler is None:
        raise RuntimeError("No handler bound")

    out = handler(args)
    print(_as_jsonable(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
