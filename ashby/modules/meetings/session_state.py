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
            "version": 2,
            "session_id": session_id,
            "active_speaker_overlay_id": None,
            "active_transcript_version_id": None,
            "speaker_overlays_by_transcript": {},
            "updated_ts": None,
        }
    payload = json.loads(p.read_text(encoding="utf-8"))
    # Back-compat: older state files may not carry the transcript pointer key.
    if "active_transcript_version_id" not in payload:
        payload["active_transcript_version_id"] = None
    if "speaker_overlays_by_transcript" not in payload or not isinstance(payload.get("speaker_overlays_by_transcript"), dict):
        payload["speaker_overlays_by_transcript"] = {}

    normalized: Dict[str, Optional[str]] = {}
    for key, value in dict(payload.get("speaker_overlays_by_transcript") or {}).items():
        k = str(key or "").strip()
        if not k:
            continue
        if value is None:
            normalized[k] = None
        else:
            v = str(value or "").strip()
            normalized[k] = v or None
    payload["speaker_overlays_by_transcript"] = normalized

    # Back-compat bridge: if legacy active pointer exists for active transcript, backfill map.
    active_trv = payload.get("active_transcript_version_id")
    active_ovr = payload.get("active_speaker_overlay_id")
    if isinstance(active_trv, str) and active_trv.strip():
        trv = active_trv.strip()
        if trv not in payload["speaker_overlays_by_transcript"]:
            if active_ovr is None:
                payload["speaker_overlays_by_transcript"][trv] = None
            else:
                ovr = str(active_ovr).strip()
                payload["speaker_overlays_by_transcript"][trv] = ovr or None

    payload["version"] = 2
    return payload


def set_active_speaker_overlay(session_id: str, overlay_id: Optional[str]) -> Dict[str, Any]:
    s = load_session_state(session_id)
    active_trv = s.get("active_transcript_version_id")
    if isinstance(active_trv, str) and active_trv.strip():
        s.setdefault("speaker_overlays_by_transcript", {})
        s["speaker_overlays_by_transcript"][active_trv.strip()] = overlay_id
    s["active_speaker_overlay_id"] = overlay_id
    s["updated_ts"] = time.time()
    save_manifest_atomic_overwrite(_state_path(session_id), s)
    return s


def set_active_transcript_version(session_id: str, transcript_version_id: Optional[str]) -> Dict[str, Any]:
    s = load_session_state(session_id)
    s["active_transcript_version_id"] = transcript_version_id
    overlays = s.get("speaker_overlays_by_transcript") if isinstance(s.get("speaker_overlays_by_transcript"), dict) else {}
    if isinstance(transcript_version_id, str) and transcript_version_id.strip():
        s["active_speaker_overlay_id"] = overlays.get(transcript_version_id.strip())
    else:
        s["active_speaker_overlay_id"] = None
    s["updated_ts"] = time.time()
    save_manifest_atomic_overwrite(_state_path(session_id), s)
    return s


def get_speaker_overlay_for_transcript(session_id: str, transcript_version_id: str) -> Optional[str]:
    trv = str(transcript_version_id or "").strip()
    if not trv:
        return None
    s = load_session_state(session_id)
    overlays = s.get("speaker_overlays_by_transcript") if isinstance(s.get("speaker_overlays_by_transcript"), dict) else {}
    if trv in overlays:
        return overlays.get(trv)
    active_trv = s.get("active_transcript_version_id")
    if isinstance(active_trv, str) and active_trv.strip() == trv:
        val = s.get("active_speaker_overlay_id")
        if val is None:
            return None
        v = str(val).strip()
        return v or None
    return None


def set_speaker_overlay_for_transcript(
    session_id: str, transcript_version_id: str, overlay_id_or_none: Optional[str]
) -> Dict[str, Any]:
    trv = str(transcript_version_id or "").strip()
    if not trv:
        raise ValueError("transcript_version_id is required")
    s = load_session_state(session_id)
    s.setdefault("speaker_overlays_by_transcript", {})
    s["speaker_overlays_by_transcript"][trv] = overlay_id_or_none
    active_trv = s.get("active_transcript_version_id")
    if isinstance(active_trv, str) and active_trv.strip() == trv:
        s["active_speaker_overlay_id"] = overlay_id_or_none
    s["updated_ts"] = time.time()
    save_manifest_atomic_overwrite(_state_path(session_id), s)
    return s


def seed_speaker_overlay_for_new_transcript(
    session_id: str, transcript_version_id: str, *, source_transcript_version_id: Optional[str] = None
) -> Dict[str, Any]:
    trv = str(transcript_version_id or "").strip()
    if not trv:
        raise ValueError("transcript_version_id is required")
    s = load_session_state(session_id)
    s.setdefault("speaker_overlays_by_transcript", {})
    overlays = s["speaker_overlays_by_transcript"]
    if trv in overlays:
        return s

    src = str(source_transcript_version_id or "").strip()
    if not src:
        active = s.get("active_transcript_version_id")
        src = str(active).strip() if isinstance(active, str) else ""

    seeded: Optional[str] = None
    if src and src in overlays:
        seeded = overlays.get(src)
    elif src:
        val = s.get("active_speaker_overlay_id")
        if val is None:
            seeded = None
        else:
            v = str(val).strip()
            seeded = v or None
    overlays[trv] = seeded
    s["updated_ts"] = time.time()
    save_manifest_atomic_overwrite(_state_path(session_id), s)
    return s


def clear_active_transcript_version(session_id: str) -> Dict[str, Any]:
    return set_active_transcript_version(session_id, None)
