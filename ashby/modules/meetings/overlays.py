from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.ids import new_id
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import save_manifest_write_once


def _overlay_dir(session_id: str) -> Path:
    lay = init_stuart_root()
    d = lay.overlays / session_id / "speaker_map"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _canonicalize_speaker_map(mapping: Dict[str, str]) -> Dict[str, str]:
    """Canonicalize speaker label -> name mappings.

    Rules:
    - keys are normalized to upper-case (e.g., SPEAKER_00)
    - values are trimmed (names are case-preserving)
    - empty keys/values are dropped
    """
    out: Dict[str, str] = {}
    if not isinstance(mapping, dict):
        return out
    for k, v in mapping.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        label = k.strip().upper()
        name = v.strip()
        if not label or not name:
            continue
        out[label] = name
    return out


def create_speaker_map_overlay(session_id: str, mapping: Dict[str, str], *, author: Optional[str] = None) -> Dict[str, Any]:
    """Append-only overlay artifact: SPEAKER_00 -> "Greg" etc.

    Quest 068 contract:
    - overlay artifacts are immutable (write-once)
    - overlay descriptor returned includes overlay_id, mapping, sha256, created_ts
    """
    canon = _canonicalize_speaker_map(mapping)
    if not canon:
        raise ValueError("speaker map overlay mapping empty")

    overlay_id = new_id("ovr")
    d = _overlay_dir(session_id)
    path = d / f"{overlay_id}.json"

    created_ts = time.time()
    payload = {
        "version": 1,
        "overlay_id": overlay_id,
        "kind": "speaker_map",
        "session_id": session_id,
        "author": author,
        "created_ts": created_ts,
        "mapping": canon,
    }
    save_manifest_write_once(path, payload)

    h = sha256_file(path)
    return {
        "overlay_id": overlay_id,
        "kind": "speaker_map",
        "session_id": session_id,
        "author": author,
        "path": str(path),
        "sha256": h,
        "created_ts": created_ts,
        "mapping": canon,
        "mapping_count": len(canon),
    }


def load_speaker_map_overlay(session_id: str, overlay_id: str) -> Dict[str, str]:
    p = _overlay_dir(session_id) / f"{overlay_id}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    m = data.get("mapping")
    if not isinstance(m, dict):
        return {}
    return _canonicalize_speaker_map(m)
