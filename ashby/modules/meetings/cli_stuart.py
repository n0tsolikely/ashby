from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.overlays import create_speaker_map_overlay
from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.primary_outputs import resolve_primary_outputs
from ashby.modules.meetings.router.router import build_intent_and_plan
from ashby.modules.meetings.schemas.plan import SessionContext
from ashby.modules.meetings.schemas.run_request import RunRequest
from ashby.modules.meetings.session_state import set_active_speaker_overlay
from ashby.modules.meetings.store import add_contribution, create_run, create_session, get_run_state
from ashby.modules.meetings.export import export_session_bundle
from ashby.modules.meetings.index import connect as idx_connect, ensure_schema as idx_ensure_schema, get_db_path, search as idx_search
from ashby.modules.meetings.schemas.search import CitationAnchor


def _as_jsonable(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, Path):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _resolve_session_id(args: argparse.Namespace) -> str:
    """Resolve session id from either positional arg or --session option."""
    sid = getattr(args, "session", None) or getattr(args, "session_id", None)
    sid = str(sid).strip() if sid is not None else ""
    if not sid:
        raise ValueError("session_id required (use --session ses_...)")
    return sid


def _run_request_from_args(args: argparse.Namespace) -> RunRequest:
    """Build a door-facing RunRequest from CLI args (no heuristics)."""
    payload: Dict[str, Any] = {
        "mode": getattr(args, "mode", None),
        "template_id": getattr(args, "template", None),
        "retention": getattr(args, "retention", None),
        "speakers": getattr(args, "speakers", None),
    }
    return RunRequest.from_dict(payload)


def _attach_primary_outputs(out: Dict[str, Any], run_id: str) -> None:
    """Attach primary output pointers + flattened paths using run manifest pointers."""
    try:
        po = resolve_primary_outputs(run_id)
    except Exception:
        po = {}

    out["primary_outputs"] = po

    paths: Dict[str, str] = {}
    if isinstance(po, dict):
        for k, v in po.items():
            if isinstance(v, dict) and isinstance(v.get("path"), str):
                paths[str(k)] = v["path"]
    out["output_paths"] = paths


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

    out: Dict[str, Any] = {
        "ok": True,
        "session_id": session_id,
        "run_id": run_id,
        "status": state.get("status"),
        "state": _as_jsonable(state),
    }
    _attach_primary_outputs(out, run_id)
    return out


def _router_formalize_plan(
    *,
    session_id: str,
    rr: RunRequest,
    extra_formalize_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a deterministic plan via the router from a door-facing RunRequest."""

    session = SessionContext(active_session_id=session_id, last_run_id=None)
    out = build_intent_and_plan(text="run", run_request=rr, session=session)

    if not out.plan.validation.ok:
        raise ValueError(f"Invalid run request: {out.plan.validation.issues}")

    steps = [{"kind": s.kind.value, "params": dict(s.params)} for s in out.plan.steps]

    if extra_formalize_params:
        for st in steps:
            if (st.get("kind") or "").strip().lower() == "formalize":
                params = st.get("params") or {}
                if not isinstance(params, dict):
                    params = {}
                params.update(extra_formalize_params)
                st["params"] = params
                break

    return {"steps": steps}


def cmd_plan(args: argparse.Namespace) -> Dict[str, Any]:
    session_id = _resolve_session_id(args)
    rr = _run_request_from_args(args)

    extra: Dict[str, Any] = {}
    if getattr(args, "contribution_id", ""):
        extra["contribution_id"] = args.contribution_id

    plan = _router_formalize_plan(session_id=session_id, rr=rr, extra_formalize_params=(extra or None))
    out = _make_run(session_id, plan, auto_go=False)
    out["status"] = "pending_go"
    return out


def cmd_go(args: argparse.Namespace) -> Dict[str, Any]:
    run_job(args.run_id)
    state = get_run_state(args.run_id)

    out: Dict[str, Any] = {
        "ok": True,
        "run_id": args.run_id,
        "status": state.get("status"),
        "state": _as_jsonable(state),
    }
    _attach_primary_outputs(out, args.run_id)
    return out


def cmd_run(args: argparse.Namespace) -> Dict[str, Any]:
    """Create and execute a run.

    Confirmation rail:
      - If --yes is not set, we DO NOT create a run and we DO NOT execute.
      - We return a plan preview so the operator can confirm.
    """

    session_id = _resolve_session_id(args)
    rr = _run_request_from_args(args)

    extra: Dict[str, Any] = {}
    if getattr(args, "contribution_id", ""):
        extra["contribution_id"] = args.contribution_id

    plan = _router_formalize_plan(session_id=session_id, rr=rr, extra_formalize_params=(extra or None))

    if not getattr(args, "yes", False):
        return {
            "ok": True,
            "status": "needs_confirm",
            "session_id": session_id,
            "run_request": rr.__dict__,
            "plan": plan,
            "message": "Confirmation required. Re-run with --yes to execute, or use 'stuart plan' then 'stuart go'.",
        }

    return _make_run(session_id, plan, auto_go=True)


def cmd_status(args: argparse.Namespace) -> Dict[str, Any]:
    state = get_run_state(args.run_id)
    out = {"ok": True, "state": _as_jsonable(state)}
    return out


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
    rr = _run_request_from_args(args)
    plan = _router_formalize_plan(
        session_id=args.session_id,
        rr=rr,
        extra_formalize_params={"reuse_run_id": args.source_run_id},
    )
    return _make_run(args.session_id, plan, auto_go=True)


def cmd_extract(args: argparse.Namespace) -> Dict[str, Any]:
    plan = {"steps": [{"kind": "extract_only", "params": {"query": args.who}}]}
    return _make_run(args.session_id, plan, auto_go=True)


def cmd_search(args: argparse.Namespace) -> Dict[str, Any]:
    """Search the library via SQLite FTS.

    Contract (D4 + D5): ranked sessions/snippets with citation anchors.
    Rails:
      - does NOT create a run
      - does NOT open artifacts
    """

    q = (getattr(args, "query", "") or "").strip()
    if not q:
        return {"ok": True, "query": q, "sessions": [], "total_hits": 0, "message": "Empty query."}

    session_filter = (getattr(args, "session_id", None) or "").strip() or None
    mode_filter = (getattr(args, "mode", None) or "").strip() or None
    limit = int(getattr(args, "limit", 10) or 10)

    db_path = get_db_path()
    conn = idx_connect(db_path)
    try:
        idx_ensure_schema(conn)
        hits = idx_search(conn, q, limit=limit, session_id=session_filter, mode=mode_filter)
    finally:
        conn.close()

    # Group by session_id (sessions-first output)
    by_ses: Dict[str, Dict[str, Any]] = {}
    for h in hits:
        sid = h.session_id
        if sid not in by_ses:
            by_ses[sid] = {
                "session_id": sid,
                "title": h.title,
                "mode": h.mode,
                "best_score": float(h.score),
                "hits": [],
            }
        else:
            by_ses[sid]["best_score"] = float(min(by_ses[sid]["best_score"], float(h.score)))
            # Prefer first non-empty title/mode
            if not by_ses[sid].get("title") and h.title:
                by_ses[sid]["title"] = h.title
            if not by_ses[sid].get("mode") and h.mode:
                by_ses[sid]["mode"] = h.mode

        cit = CitationAnchor(
            session_id=h.session_id,
            run_id=h.run_id,
            segment_id=int(h.segment_id),
            speaker_label=h.speaker_label,
            t_start=h.t_start,
            t_end=h.t_end,
            source_path=h.source_path,
        ).to_dict()

        by_ses[sid]["hits"].append(
            {
                "score": float(h.score),
                "snippet": h.snippet,
                "citation": cit,
            }
        )

    sessions = list(by_ses.values())
    # Deterministic ordering: best score asc, then session_id
    sessions.sort(key=lambda s: (float(s.get("best_score", 0.0)), str(s.get("session_id"))))
    # Deterministic ordering within session: score asc
    for s in sessions:
        s["hits"].sort(key=lambda it: float(it.get("score", 0.0)))

    return {
        "ok": True,
        "query": q,
        "limit": limit,
        "session_filter": session_filter,
        "mode_filter": mode_filter,
        "total_hits": int(len(hits)),
        "sessions": sessions,
    }


def cmd_export(args: argparse.Namespace) -> Dict[str, Any]:
    """Export a session bundle zip.

    CLI surface for the export bundle primitive.
    """
    session_id = (getattr(args, "session_id", None) or "").strip()
    if not session_id:
        raise ValueError("--session is required")

    out_raw = (getattr(args, "out", None) or "").strip() or None
    out_path = Path(out_raw).expanduser().resolve() if out_raw else None

    res = export_session_bundle(session_id, out_path=out_path)
    return {"ok": True, **res.to_dict()}



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
    pl.add_argument("session_id", nargs="?", default=None, help="Existing session id (ses_...)")
    pl.add_argument("--session", dest="session", default=None, help="Existing session id (ses_...)")
    pl.add_argument("--mode", choices=["meeting", "journal"], default="meeting")
    pl.add_argument("--template", default="default")
    pl.add_argument("--retention", default=None)
    pl.add_argument("--speakers", default=None)
    pl.add_argument("--contribution-id", default="")
    pl.set_defaults(_handler=cmd_plan)

    go = sub.add_parser("go", help="Execute an existing run_id.")
    go.add_argument("run_id", help="Run ID (run_...)")
    go.set_defaults(_handler=cmd_go)

    rn = sub.add_parser("run", help="Build plan, require confirm, then execute processing.")
    rn.add_argument("session_id", nargs="?", default=None, help="Existing session id (ses_...)")
    rn.add_argument("--session", dest="session", default=None, help="Existing session id (ses_...)")
    rn.add_argument("--mode", choices=["meeting", "journal"], default="meeting")
    rn.add_argument("--template", default="default")
    rn.add_argument("--retention", default=None)
    rn.add_argument("--speakers", default=None)
    rn.add_argument("--contribution-id", default="")
    rn.add_argument("--yes", action="store_true", help="Confirm and execute (otherwise returns plan preview).")
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
    rr.add_argument("--retention", default=None)
    rr.add_argument("--speakers", default=None)
    rr.set_defaults(_handler=cmd_rerender)

    ex = sub.add_parser("extract", help="Export only what a named speaker said (requires active mapping).")
    ex.add_argument("session_id", help="Session id (ses_...)")
    ex.add_argument("who", help="Speaker name (must match active overlay mapping)")
    ex.set_defaults(_handler=cmd_extract)

    sr = sub.add_parser("search", help="Search the library via SQLite FTS (sessions/snippets + citations).")
    sr.add_argument("query", help="Search query text")
    sr.add_argument("--session", dest="session_id", default=None, help="Optional session id (ses_...)")
    sr.add_argument("--mode", choices=["meeting", "journal"], default=None, help="Optional mode filter")
    sr.add_argument("--limit", type=int, default=10)
    sr.set_defaults(_handler=cmd_search)


    exp = sub.add_parser("export", help="Export a session bundle zip (read-only copy).")
    exp.add_argument("--session", dest="session_id", required=True, help="Session id (ses_...)")
    exp.add_argument("--out", dest="out", default=None, help="Optional output zip path (default: STUART_ROOT/exports).")
    exp.set_defaults(_handler=cmd_export)

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
