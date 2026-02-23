from __future__ import annotations

import json

from pathlib import Path
from typing import Any, Dict, Optional


def transcript_version_id_for_run(run_id: str) -> str:
    return f"tv__{run_id}"


def run_id_from_transcript_version_id(transcript_version_id: str) -> Optional[str]:
    v = str(transcript_version_id or "").strip()
    if not v.startswith("tv__"):
        return None
    rid = v[4:]
    return rid if rid.startswith("run_") and len(rid) > 4 else None


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize_segment(seg: Dict[str, Any], idx: int, run_id: str) -> Dict[str, Any]:
    def as_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    return {
        "segment_id": str(seg.get("segment_id") or f"{run_id}_{idx}"),
        "speaker": str(seg.get("speaker") or seg.get("speaker_label") or "").strip() or None,
        "start_time": as_float(seg.get("start_time", seg.get("start"))),
        "end_time": as_float(seg.get("end_time", seg.get("end"))),
        "text": str(seg.get("text") or "").strip(),
        "confidence": seg.get("confidence"),
    }
