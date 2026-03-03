from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi.responses import Response

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.primary_outputs import resolve_primary_outputs


def list_run_artifacts(run_id: str) -> List[Dict[str, Any]]:
    """List downloadable files for a run.

    We expose both:
      - runs/<run_id>/artifacts (ground truth + derived)
      - runs/<run_id>/exports   (pdf exports, etc.)

    Note:
      For deterministic "primary" downloads (minutes.pdf/journal.pdf), prefer
      `primary_downloads(...)` which is derived from run.json['primary_outputs'].
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


def primary_downloads(run_id: str, *, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return deterministic download links for primary outputs.

    HARD RULE (QUEST_063): use run.json['primary_outputs'] pointers.
    Do not guess filenames.

    Returns:
      {
        "mode": "meeting"|"journal"|None,
        "primary": {
          "pdf": {"kind","name","url","sha256","created_ts"},
          "md":  {..},
          "json": {..},
          "evidence_map": {..}
        }
      }
    """

    po: Optional[Dict[str, Any]] = None
    if isinstance(state, dict):
        maybe = state.get("primary_outputs")
        if isinstance(maybe, dict) and maybe:
            po = maybe

    if po is None:
        # Falls back to deriving from artifacts if primary_outputs is missing.
        # (We do NOT auto-write back here; job_runner should populate it.)
        po = resolve_primary_outputs(run_id)

    primary: Dict[str, Any] = {}

    def add_ptr(key: str) -> None:
        ptr = po.get(key)
        if not isinstance(ptr, dict):
            return
        path = ptr.get("path")
        if not isinstance(path, str) or not path:
            return
        name = Path(path).name
        primary[key] = {
            "kind": ptr.get("kind"),
            "name": name,
            "url": f"/download/{quote(run_id)}/{quote(name)}",
            "sha256": ptr.get("sha256"),
            "created_ts": ptr.get("created_ts"),
        }

    for k in ("pdf", "md", "txt", "json", "evidence_map", "transcript"):
        add_ptr(k)

    return {
        "mode": po.get("mode"),
        "primary": primary,
    }


def artifact_response(run_id: str, filename: str) -> Response:
    lay = init_stuart_root()
    run_dir = lay.runs / run_id

    for sub in ("artifacts", "exports"):
        p = run_dir / sub / filename
        if p.exists():
            data = p.read_bytes()
            return Response(
                content=data,
                media_type="application/octet-stream",
                headers={"content-disposition": f'attachment; filename="{filename}"'},
            )

    raise FileNotFoundError(filename)
