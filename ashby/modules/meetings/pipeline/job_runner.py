from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.store import get_run_state, update_run_state
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.pipeline.diarize import diarize_stub
from ashby.modules.meetings.pipeline.search import search_and_write_results
from ashby.modules.meetings.render.formalize_md import render_formalized_md
from ashby.modules.meetings.render.evidence_map import build_evidence_map
from ashby.modules.meetings.render.export_pdf import export_pdf_stub
from ashby.modules.meetings.session_state import load_session_state, set_active_speaker_overlay
from ashby.modules.meetings.overlays import create_speaker_map_overlay, load_speaker_map_overlay
from ashby.modules.meetings.render.extract_only import extract_only_by_speaker


@dataclass(frozen=True)
class RunResult:
    ok: bool
    run_id: str
    status: str
    message: str


def _steps_from_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        return []
    out: List[Dict[str, Any]] = []
    for s in steps:
        if isinstance(s, dict):
            out.append(s)
        else:
            out.append({"kind": str(s)})
    return out


def _step_kind(step: Dict[str, Any]) -> str:
    for k in ("kind", "name", "stage", "id"):
        v = step.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def _get_run_artifact_path(run_id: str, filename: str) -> Optional[Path]:
    lay = init_stuart_root()
    p = lay.runs / run_id / "artifacts" / filename
    return p if p.exists() else None


def _maybe_load_active_speaker_map(session_id: str) -> Dict[str, str]:
    st = load_session_state(session_id)
    ovr_id = st.get("active_speaker_overlay_id")
    if isinstance(ovr_id, str) and ovr_id:
        return load_speaker_map_overlay(session_id, ovr_id)
    return {}


def run_job(run_id: str) -> RunResult:
    """Execute a run plan deterministically.

    - Idempotent: do not rerun succeeded/failed runs.
    - No ground-truth mutation: overlays are append-only; session_state is pointer-only.
    """
    state = get_run_state(run_id)
    if state.get("status") in ("succeeded", "failed"):
        return RunResult(ok=True, run_id=run_id, status=str(state.get("status")), message="Run already completed.")

    session_id = state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return RunResult(ok=False, run_id=run_id, status="failed", message="Run missing session_id")

    plan = state.get("plan") if isinstance(state, dict) else {}
    steps = _steps_from_plan(plan)

    lay = init_stuart_root()
    run_dir = lay.runs / run_id

    now = time.time()
    update_run_state(run_id, status="running", stage="running", progress=0, started_ts=now)

    try:
        n = max(len(steps), 1)

        if not steps:
            update_run_state(run_id, stage="complete", progress=100)
        else:
            for i, step in enumerate(steps):
                kind = _step_kind(step)
                pct = int(((i + 1) / n) * 90)
                update_run_state(run_id, stage=kind or f"step_{i+1}", progress=pct)

                params = step.get("params") if isinstance(step, dict) else {}

                if kind == "validate":
                    # no-op: plan validation happens before run creation (kept for plan determinism)
                    pass

                if kind == "speaker_map_overlay":
                    overlay = (params or {}).get("overlay")
                    if not isinstance(overlay, dict) or not overlay:
                        raise ValueError("speaker_map_overlay missing overlay mapping")
                    mapping: Dict[str, str] = {}
                    for k, v in overlay.items():
                        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                            mapping[k.strip().upper()] = v.strip()
                    if not mapping:
                        raise ValueError("speaker_map_overlay mapping empty")
                    ovr = create_speaker_map_overlay(session_id, mapping)
                    set_active_speaker_overlay(session_id, ovr["overlay_id"])
                    update_run_state(run_id, artifact={"kind": "speaker_map_overlay", "path": ovr["path"], "sha256": ovr["sha256"], "created_ts": ovr["created_ts"]})

                elif kind == "formalize":
                    # If caller provided reuse_run_id, reuse transcript artifact instead of regenerating.
                    reuse_run_id = (params or {}).get("reuse_run_id")
                    transcript_path: Optional[Path] = None
                    if isinstance(reuse_run_id, str) and reuse_run_id:
                        transcript_path = _get_run_artifact_path(reuse_run_id, "transcript.txt")
                    if transcript_path is None:
                        a1 = transcribe_stub(run_dir)
                        update_run_state(run_id, artifact=a1)
                        transcript_path = Path(a1["path"])  # created

                    # diarization stub is allowed, but not required for QUEST_007.
                    a2 = diarize_stub(run_dir)
                    update_run_state(run_id, artifact=a2)

                    mode = (params or {}).get("mode") or "meeting"
                    template_id = (params or {}).get("template") or "default"
                    speaker_map = _maybe_load_active_speaker_map(session_id)
                    a3 = render_formalized_md(run_dir, mode=mode, template_id=template_id, transcript_path=transcript_path, speaker_map=speaker_map)
                    update_run_state(run_id, artifact=a3)
                    a4 = build_evidence_map(run_dir)
                    update_run_state(run_id, artifact=a4)
                    a5 = export_pdf_stub(run_dir, md_path=run_dir / "artifacts" / "formalized.md")
                    update_run_state(run_id, artifact=a5)

                elif kind == "search":
                    q = (params or {}).get("query")
                    if not isinstance(q, str):
                        q = str(q) if q is not None else ""
                    sess_filter = (params or {}).get("session_id")
                    if sess_filter is None:
                        sess_filter = session_id
                    if isinstance(sess_filter, str) and sess_filter.strip() == "":
                        sess_filter = None
                    if sess_filter is not None and not isinstance(sess_filter, str):
                        sess_filter = str(sess_filter)
                    lim = (params or {}).get("limit", 10)
                    try:
                        lim_i = int(lim)
                    except Exception:
                        lim_i = 10
                    a_search = search_and_write_results(run_dir, query=q, session_id=sess_filter, limit=lim_i)
                    update_run_state(run_id, artifact=a_search)

                elif kind == "extract_only":
                    who = (params or {}).get("query")
                    if not isinstance(who, str) or not who.strip():
                        raise ValueError("extract_only requires query (speaker name)")
                    # Determine speaker_label from active speaker map
                    speaker_map = _maybe_load_active_speaker_map(session_id)
                    # reverse mapping: name -> label
                    wanted = who.strip()
                    label = None
                    for k, v in speaker_map.items():
                        if v == wanted:
                            label = k
                            break
                    if label is None:
                        raise ValueError(f"No active speaker mapping for '{wanted}'. Set mapping first.")

                    # Prefer reusing transcript from last run if available
                    last_run_id = state.get("last_run_id") if isinstance(state.get("last_run_id"), str) else None
                    transcript_path = _get_run_artifact_path(last_run_id, "transcript.txt") if last_run_id else None
                    if transcript_path is None:
                        # Fall back: ensure transcript exists for this run
                        a1 = transcribe_stub(run_dir)
                        update_run_state(run_id, artifact=a1)
                        transcript_path = Path(a1["path"])

                    out_dir = run_dir / "artifacts" / "extract_only"
                    ex = extract_only_by_speaker(out_dir=out_dir, transcript_path=transcript_path, speaker_label=label, speaker_name=wanted, speaker_map=speaker_map)
                    update_run_state(run_id, artifact={"kind": "extract_only", "path": ex["paths"]["json"], "sha256": ex["sha256"]["json"], "created_ts": ex["created_ts"]})
                    pdf = export_pdf_stub(run_dir, md_path=Path(ex["paths"]["md"]), out_name="extract_only.pdf")
                    update_run_state(run_id, artifact=pdf)

                # update progress after step
                update_run_state(run_id, stage=kind or f"step_{i+1}", progress=pct)

        end = time.time()
        update_run_state(run_id, status="succeeded", stage="succeeded", progress=100, ended_ts=end)
        return RunResult(ok=True, run_id=run_id, status="succeeded", message="Run completed.")
    except Exception as e:
        end = time.time()
        err = {"type": e.__class__.__name__, "message": str(e)}
        update_run_state(run_id, status="failed", stage="failed", progress=int(state.get("progress") or 0), ended_ts=end, error=err)
        return RunResult(ok=False, run_id=run_id, status="failed", message=str(e))


def poll_progress(run_id: str) -> Dict[str, Any]:
    s = get_run_state(run_id)
    return {
        "run_id": run_id,
        "status": s.get("status"),
        "stage": s.get("stage"),
        "progress": s.get("progress"),
        "started_ts": s.get("started_ts"),
        "ended_ts": s.get("ended_ts"),
    }
