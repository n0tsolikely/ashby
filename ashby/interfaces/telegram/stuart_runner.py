from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import re

from ashby.modules.meetings.schemas.run_request import RunRequest


def _py() -> str:
    # Allow Ashby Telegram to run Stuart in a separate venv / python version.
    return os.environ.get("STUART_PYTHON") or sys.executable


def _env() -> Dict[str, str]:
    env = dict(os.environ)

    # Inject canonical repo root into PYTHONPATH for subprocesses
    repo_root = Path(__file__).resolve().parents[3]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo_root) + (os.pathsep + existing if existing else "")

    sr = env.get("STUART_ROOT")
    if sr:
        env["STUART_ROOT"] = sr
    return env


def _run_cmd(args: list[str]) -> Dict[str, Any]:
    p = subprocess.run(args, check=True, capture_output=True, text=True, env=_env())
    out = (p.stdout or "").strip()
    # cli_stuart prints a Python dict. Parse safely.
    return ast.literal_eval(out) if out else {}


def _extract_primary_pdf_path(run_state: Dict[str, Any]) -> Optional[str]:
    """Extract the canonical primary PDF pointer from a cli_stuart run/go response."""
    st = run_state.get("state") if isinstance(run_state, dict) else None
    if not isinstance(st, dict):
        return None
    po = st.get("primary_outputs")
    if not isinstance(po, dict):
        return None
    pdf = po.get("pdf")
    if not isinstance(pdf, dict):
        return None
    p = pdf.get("path")
    return p if isinstance(p, str) and p else None


def run_default_pipeline(
    *,
    local_path: str,
    source_kind: str,
    run_request: RunRequest,
    template: str = "default",
    retention: str = "MED",
    contribution_id: str | None = None,
) -> Dict[str, Any]:
    """Telegram subprocess runner: upload -> plan (in-proc) -> go (subprocess) -> return primary PDF.

    Contract:
    - Do NOT auto-run on upload.
    - Always return the mode-specific primary PDF (minutes.pdf / journal.pdf) via run.primary_outputs pointers.
    """

    # 1) upload (creates session if none)
    kind_flag = source_kind if source_kind in ("audio", "video") else "audio"
    mode = (run_request.mode or "meeting").strip().lower() if isinstance(run_request.mode, str) else "meeting"
    up = _run_cmd(
        [
            _py(),
            "-m",
            "ashby.modules.meetings.cli_stuart",
            "upload",
            local_path,
            "--kind",
            kind_flag,
            "--mode",
            mode,
        ]
    )
    session_id = up.get("session_id")
    uploaded_contribution_id = up.get("contribution_id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError(f"upload did not return session_id: {up}")

    cid = contribution_id or (
        uploaded_contribution_id if isinstance(uploaded_contribution_id, str) and uploaded_contribution_id else None
    )

    # 2) Build a deterministic plan from the unified RunRequest contract (in-proc),
    # then create the run manifest. Execution still happens via subprocess (go).
    from ashby.modules.meetings.router.router import build_intent_and_plan
    from ashby.modules.meetings.schemas.plan import SessionContext
    from ashby.modules.meetings.store import create_run

    rr = RunRequest(
        mode=mode,
        template_id=(run_request.template_id or template),
        retention=(run_request.retention or retention),
        speakers=run_request.speakers,
    )

    session = SessionContext(active_session_id=session_id, last_run_id=None)
    out = build_intent_and_plan(text="run", run_request=rr, session=session)
    if not out.plan.validation.ok:
        raise ValueError(f"Invalid run request: {out.plan.validation.issues}")

    steps = [{"kind": s.kind.value, "params": dict(s.params)} for s in out.plan.steps]

    if cid:
        for st in steps:
            if (st.get("kind") or "").strip().lower() == "formalize":
                params = st.get("params") if isinstance(st.get("params"), dict) else {}
                params = dict(params)
                params["contribution_id"] = cid
                st["params"] = params
                break

    run_id = create_run(session_id=session_id, plan={"steps": steps})

    # 3) execute in subprocess
    rn = _run_cmd([
        _py(), "-m", "ashby.modules.meetings.cli_stuart", "go", run_id
    ])

    # 4) return the canonical primary PDF pointer
    pdf_path = _extract_primary_pdf_path(rn)

    po: Dict[str, Any] = {}
    st = rn.get("state") if isinstance(rn, dict) else None
    if isinstance(st, dict) and isinstance(st.get("primary_outputs"), dict):
        po = dict(st.get("primary_outputs") or {})

    if not pdf_path:
        # Fallback: resolve from run state on disk.
        from ashby.modules.meetings.primary_outputs import resolve_primary_outputs

        po = resolve_primary_outputs(run_id)
        pdf = po.get("pdf") if isinstance(po, dict) else None
        if isinstance(pdf, dict):
            p = pdf.get("path")
            pdf_path = p if isinstance(p, str) and p else None

    return {
        "ok": True,
        "session_id": session_id,
        "contribution_id": cid,
        "run_id": run_id,
        "run": rn,
        "primary_outputs": po,
        "pdf_path": pdf_path,
    }


_SPEAKER_LINE_RE = re.compile(
    r"^(?P<label>speaker_\d{2})\s*(?:is|=|:)\s*(?P<name>.+?)\s*$",
    flags=re.IGNORECASE,
)


def _parse_speaker_map_text(text: str) -> Dict[str, str]:
    """Parse Telegram user text into a speaker label -> name mapping.

    Supported minimal formats (case-insensitive):
      - "SPEAKER_00 is Greg"
      - "SPEAKER_00 = Greg"
      - "SPEAKER_00: Greg"

    Multiple mappings can be provided on separate lines.
    """

    out: Dict[str, str] = {}
    raw = (text or "").strip()
    if not raw:
        return out

    for line in raw.splitlines():
        ln = line.strip()
        if not ln:
            continue
        m = _SPEAKER_LINE_RE.match(ln)
        if not m:
            continue
        label = (m.group("label") or "").strip().upper()
        name = (m.group("name") or "").strip()
        if not label or not name:
            continue
        if not label.startswith("SPEAKER_"):
            continue
        out[label] = name
    return out


def telegram_set_speaker_map(
    *,
    session_id: str,
    mapping_text: str,
    author: Optional[str] = "telegram",
) -> Dict[str, Any]:
    """Set/extend the active speaker map overlay for a session.

    Telegram UX is typically incremental (users send multiple messages).
    To avoid losing prior mappings, we merge with any active overlay mapping
    and write a new append-only overlay snapshot.

    Returns overlay descriptor + updated session_state pointer.
    """

    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id required")

    mapping = _parse_speaker_map_text(mapping_text)
    if not mapping:
        raise ValueError("No speaker mappings found (expected lines like 'SPEAKER_00 is Greg').")

    # Import in-proc: overlay artifacts are pure JSON and do not require heavy deps.
    from ashby.modules.meetings.overlays import create_speaker_map_overlay, load_speaker_map_overlay
    from ashby.modules.meetings.session_state import load_session_state, set_active_speaker_overlay

    # Merge with current active mapping if present.
    merged: Dict[str, str] = {}
    try:
        st0 = load_session_state(session_id)
        ovr0 = st0.get("active_speaker_overlay_id")
        if isinstance(ovr0, str) and ovr0.strip():
            merged.update(load_speaker_map_overlay(session_id, ovr0.strip()))
    except Exception:
        merged = {}

    merged.update({k.strip().upper(): v.strip() for k, v in mapping.items() if k and v})

    ovr = create_speaker_map_overlay(session_id, merged, author=author)
    st = set_active_speaker_overlay(session_id, ovr["overlay_id"])
    return {"ok": True, "session_id": session_id, "overlay": ovr, "session_state": st}


def telegram_reformalize_minimal(
    *,
    session_id: str,
    source_run_id: str,
    run_request: RunRequest,
    template: str = "default",
    retention: str = "MED",
) -> Dict[str, Any]:
    """Trigger a formalize-only rerun using the active overlay, reusing transcript artifacts.

    This is the minimal Telegram loop (QUEST_072):
      1) set overlay mapping
      2) re-formalize without retranscribing
      3) return updated primary PDF path
    """

    sid = (session_id or "").strip()
    rid = (source_run_id or "").strip()
    if not sid:
        raise ValueError("session_id required")
    if not rid:
        raise ValueError("source_run_id required")

    mode = (run_request.mode or "meeting").strip().lower() if isinstance(run_request.mode, str) else "meeting"
    tpl = (run_request.template_id or template).strip() if isinstance(run_request.template_id, str) else template

    rr_ret = run_request.retention if isinstance(run_request.retention, str) and run_request.retention.strip() else None
    rr_spk = run_request.speakers

    args = [
        _py(),
        "-m",
        "ashby.modules.meetings.cli_stuart",
        "rerender",
        sid,
        rid,
        "--mode",
        mode,
        "--template",
        tpl,
    ]
    if rr_ret is not None:
        args.extend(["--retention", rr_ret])
    else:
        # Keep v1 default consistent when not specified by caller.
        args.extend(["--retention", retention])

    if rr_spk is not None:
        args.extend(["--speakers", str(rr_spk)])

    out = _run_cmd(args)
    pdf_path = _extract_primary_pdf_path(out)

    po: Dict[str, Any] = {}
    st = out.get("state") if isinstance(out, dict) else None
    if isinstance(st, dict) and isinstance(st.get("primary_outputs"), dict):
        po = dict(st.get("primary_outputs") or {})

    if not pdf_path:
        # Fallback: resolve from run state on disk.
        from ashby.modules.meetings.primary_outputs import resolve_primary_outputs

        run_id = out.get("run_id") if isinstance(out.get("run_id"), str) else None
        if run_id:
            po = resolve_primary_outputs(run_id)
            pdf = po.get("pdf") if isinstance(po, dict) else None
            if isinstance(pdf, dict) and isinstance(pdf.get("path"), str):
                pdf_path = pdf.get("path")

    return {
        "ok": True,
        "session_id": sid,
        "source_run_id": rid,
        "run_id": out.get("run_id"),
        "run": out,
        "primary_outputs": po,
        "pdf_path": pdf_path,
    }
