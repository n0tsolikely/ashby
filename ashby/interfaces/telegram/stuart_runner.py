from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


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


def _extract_pdf_path(run_state: Dict[str, Any]) -> Optional[str]:
    st = run_state.get("state") if isinstance(run_state, dict) else None
    if not isinstance(st, dict):
        return None

    artifacts = st.get("artifacts")
    if not isinstance(artifacts, list):
        return None

    # Prefer canonical formalized PDF
    for a in artifacts:
        if isinstance(a, dict) and a.get("kind") == "formalized_pdf":
            p = a.get("path")
            if isinstance(p, str) and p:
                return p

    # Fallback: any PDF artifact path
    for a in artifacts:
        if isinstance(a, dict):
            p = a.get("path")
            if isinstance(p, str) and p.lower().endswith(".pdf"):
                return p

    return None

def run_default_pipeline(*, local_path: str, source_kind: str, mode: str, template: str = "default") -> Dict[str, Any]:
    # 1) upload (creates session if none)
    up = _run_cmd([
        _py(), "-m", "ashby.modules.meetings.cli_stuart",
        "upload", local_path,
        "--kind", source_kind,
        "--mode", mode,
    ])
    session_id = up.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError(f"upload did not return session_id: {up}")

    # 2) run default template pipeline
    rn = _run_cmd([
        _py(), "-m", "ashby.modules.meetings.cli_stuart",
        "run", session_id,
        "--mode", mode,
        "--template", template,
    ])

    # 3) extract or force-export PDF
    pdf_path = _extract_pdf_path(rn)

    if not pdf_path:
        from pathlib import Path
        from ashby.modules.meetings.render.export_pdf import export_pdf_stub

        run_dir_val = rn.get("run_dir")
        if isinstance(run_dir_val, str) and run_dir_val:
            run_dir = Path(run_dir_val)
            if run_dir.exists():
                out = export_pdf_stub(run_dir)
                pdf_path = out.get("pdf_path")

                # final fallback: scan exports dir
                if not pdf_path:
                    exports = run_dir / "exports"
                    if exports.exists():
                        for p in exports.glob("*.pdf"):
                            pdf_path = str(p)
                            break

    return {
        "ok": True,
        "session_id": session_id,
        "run": rn,
        "pdf_path": pdf_path,
    }
