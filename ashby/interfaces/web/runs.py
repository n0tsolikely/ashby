from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi.responses import FileResponse

from ashby.modules.meetings.init_root import init_stuart_root


def list_run_artifacts(run_id: str) -> List[Dict[str, Any]]:
    """List downloadable files for a run.

    We expose both:
      - runs/<run_id>/artifacts (ground truth + derived)
      - runs/<run_id>/exports   (pdf exports, etc.)
    """
    lay = init_stuart_root()
    run_dir = lay.runs / run_id
    out: List[Dict[str, Any]] = []

    for sub in ("artifacts", "exports"):
        d = run_dir / sub
        if not d.exists():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            out.append({
                "name": p.name,
                "kind": sub,
                "size": p.stat().st_size,
            })
    return out


def artifact_response(run_id: str, filename: str) -> FileResponse:
    lay = init_stuart_root()
    run_dir = lay.runs / run_id

    for sub in ("artifacts", "exports"):
        p = run_dir / sub / filename
        if p.exists():
            return FileResponse(path=str(p), filename=filename)

    raise FileNotFoundError(filename)
