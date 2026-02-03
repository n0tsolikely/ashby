from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.ids import new_id
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.manifests import save_manifest_write_once


def _overlay_dir(session_id: str) -> Path:
    lay = init_stuart_root()
    d = lay.overlays / session_id / "speaker_map"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_speaker_map_overlay(session_id: str, mapping: Dict[str, str], *, author: Optional[str] = None) -> Dict[str, Any]:
    """Append-only overlay artifact: SPEAKER_00 -> "Greg" etc."""
    overlay_id = new_id("ovr")
    d = _overlay_dir(session_id)
    path = d / f"{overlay_id}.json"
    payload = {
        "version": 1,
        "overlay_id": overlay_id,
        "kind": "speaker_map",
        "session_id": session_id,
        "author": author,
        "created_ts": time.time(),
        "mapping": mapping,
    }
    save_manifest_write_once(path, payload)
    h = sha256_file(path)
    return {"overlay_id": overlay_id, "path": str(path), "sha256": h, "created_ts": payload["created_ts"]}


def load_speaker_map_overlay(session_id: str, overlay_id: str) -> Dict[str, str]:
    p = _overlay_dir(session_id) / f"{overlay_id}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    m = data.get("mapping")
    if not isinstance(m, dict):
        return {}
    # ensure str->str
    out: Dict[str, str] = {}
    for k, v in m.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out
