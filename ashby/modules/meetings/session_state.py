from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import save_manifest_atomic_overwrite


def _state_path(session_id: str) -> Path:
    lay = init_stuart_root()
    return lay.sessions / session_id / "session_state.json"


def load_session_state(session_id: str) -> Dict[str, Any]:
    """Mutable session state (pointers only). Ground truth remains immutable artifacts."""
    p = _state_path(session_id)
    if not p.exists():
        return {
            "version": 1,
            "session_id": session_id,
            "active_speaker_overlay_id": None,
            "updated_ts": None,
        }
    return json.loads(p.read_text(encoding="utf-8"))


def set_active_speaker_overlay(session_id: str, overlay_id: Optional[str]) -> Dict[str, Any]:
    s = load_session_state(session_id)
    s["active_speaker_overlay_id"] = overlay_id
    s["updated_ts"] = time.time()
    save_manifest_atomic_overwrite(_state_path(session_id), s)
    return s
