from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


_EN_DASH = "–"  # U+2013


def _hhmmss(total_seconds: int) -> str:
    if total_seconds < 0:
        total_seconds = 0
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _floor_ms_to_s(ms: int) -> int:
    if ms < 0:
        ms = 0
    return int(ms // 1000)


def _ceil_ms_to_s(ms: int) -> int:
    if ms < 0:
        ms = 0
    return int((ms + 999) // 1000)


def format_citation_token(
    segment_id: int,
    *,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    t_start: Optional[float] = None,
    t_end: Optional[float] = None,
) -> str:
    """Format a single citation token.

    Standard (v1):
      [S12@00:03:12–00:03:19]

    Notes:
    - Stable identifier is segment_id + timestamps.
    - Prefer transcript-derived start_ms/end_ms when available.
    - Fall back to t_start/t_end if provided.
    - If no timestamps are available, return [S12] (truthful fallback).
    """
    sid = int(segment_id)

    # Prefer ms (canonical transcript segment timings)
    if start_ms is not None and end_ms is not None:
        try:
            sm = int(start_ms)
            em = int(end_ms)
        except Exception:
            sm, em = 0, 0

        start_s = _floor_ms_to_s(sm)
        end_s = _ceil_ms_to_s(em)
        if end_s < start_s:
            end_s = start_s
        if end_s == start_s and em > sm:
            end_s = start_s + 1
        return f"[S{sid}@{_hhmmss(start_s)}{_EN_DASH}{_hhmmss(end_s)}]"

    # Secondary: use provided t_start/t_end (seconds)
    if t_start is not None and t_end is not None:
        try:
            ts0 = float(t_start)
            ts1 = float(t_end)
        except Exception:
            ts0, ts1 = 0.0, 0.0
        start_s = int(ts0) if ts0 >= 0 else 0
        # ceil-ish for end
        end_s = int(ts1 + 0.999) if ts1 >= 0 else 0
        if end_s < start_s:
            end_s = start_s
        if end_s == start_s and ts1 > ts0:
            end_s = start_s + 1
        return f"[S{sid}@{_hhmmss(start_s)}{_EN_DASH}{_hhmmss(end_s)}]"

    return f"[S{sid}]"


def uniq_sorted_segment_ids(citations: Any) -> List[int]:
    """Extract unique segment_ids from a citations list (stable order: numeric ascending)."""
    if not isinstance(citations, list):
        return []

    ids: List[int] = []
    seen = set()
    for c in citations:
        if not isinstance(c, dict):
            continue
        if "segment_id" not in c:
            continue
        try:
            sid = int(c["segment_id"])
        except Exception:
            continue
        if sid in seen:
            continue
        seen.add(sid)
        ids.append(sid)
    return sorted(ids)


def load_segments_by_id(run_dir: Path, *, mode: str) -> Dict[int, Dict[str, Any]]:
    """Load transcript segments and return {segment_id: segment} mapping.

    Preference:
    - meeting mode: aligned_transcript.json if present
    - otherwise: transcript.json

    Returns empty dict if no transcript JSON exists.
    """
    artifacts = run_dir / "artifacts"
    ajson = artifacts / "aligned_transcript.json"
    tjson = artifacts / "transcript.json"

    src: Optional[Path] = None
    if mode == "meeting" and ajson.exists():
        src = ajson
        # Deterministic fallback rail:
        # when transcript.json is stub-engine, keep segment anchors on transcript.json
        # so rendered citations stay stable with deterministic formalization.
        if tjson.exists():
            try:
                t_payload = json.loads(tjson.read_text(encoding="utf-8"))
                if str(t_payload.get("engine") or "").strip().lower() == "stub":
                    src = tjson
            except Exception:
                pass
    elif tjson.exists():
        src = tjson

    if not src or not src.exists():
        return {}

    payload = json.loads(src.read_text(encoding="utf-8"))
    segs = payload.get("segments") or []
    if not isinstance(segs, list):
        return {}

    out: Dict[int, Dict[str, Any]] = {}
    for s in segs:
        if not isinstance(s, dict):
            continue
        if "segment_id" not in s:
            continue
        try:
            sid = int(s.get("segment_id"))
        except Exception:
            continue
        out[sid] = s
    return out


def format_citations(citations: Any, *, segs_by_id: Optional[Dict[int, Dict[str, Any]]] = None) -> str:
    """Format a citations list into stable, readable inline tokens.

    Returns a leading-space-prefixed string suitable for appending to a line,
    or "" if no citations.
    """
    if not isinstance(citations, list):
        return ""

    ids = uniq_sorted_segment_ids(citations)
    if not ids:
        return ""

    tokens: List[str] = []
    for sid in ids:
        seg = segs_by_id.get(sid) if isinstance(segs_by_id, dict) else None
        if isinstance(seg, dict):
            tokens.append(
                format_citation_token(
                    sid,
                    start_ms=seg.get("start_ms"),
                    end_ms=seg.get("end_ms"),
                )
            )
            continue

        # Fallback: see if any anchor includes explicit t_start/t_end
        ts0: Optional[float] = None
        ts1: Optional[float] = None
        for a in citations:
            if not isinstance(a, dict):
                continue
            try:
                if int(a.get("segment_id")) != sid:
                    continue
            except Exception:
                continue
            if "t_start" in a and "t_end" in a:
                try:
                    ts0 = float(a.get("t_start"))
                    ts1 = float(a.get("t_end"))
                    break
                except Exception:
                    pass

        tokens.append(format_citation_token(sid, t_start=ts0, t_end=ts1))

    return " " + " ".join(tokens)
