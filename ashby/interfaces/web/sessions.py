from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from ashby.modules.meetings import store
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import load_manifest


def list_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    lay = init_stuart_root()
    out: List[Dict[str, Any]] = []

    if not lay.sessions.exists():
        return out

    for p in sorted(lay.sessions.iterdir(), reverse=True):
        if not p.is_dir():
            continue
        mpath = p / "session.json"
        if not mpath.exists():
            continue
        m = load_manifest(mpath)
        out.append({
            "session_id": m.get("session_id"),
            "created_ts": m.get("created_ts"),
            "mode": m.get("mode"),
            "title": m.get("title"),
            "runs": m.get("runs", []),
            "contributions": m.get("contributions", []),
        })
        if len(out) >= int(limit):
            break
    return out


def create_session(mode: str, title: Optional[str] = None) -> str:
    return store.create_session(mode=mode, title=title)
