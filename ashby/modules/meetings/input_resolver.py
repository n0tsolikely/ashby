from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Tuple


class HasContributions(Protocol):
    contributions: Path


@dataclass(frozen=True)
class ResolvedInput:
    contribution_id: str
    source_path: Path
    source_kind: str  # "audio" | "video" | etc.


def _load_manifest(con_dir: Path) -> dict:
    p = con_dir / "contribution.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _find_source_file(con_dir: Path) -> Path:
    # Stored as source<ext>, e.g., source.m4a / source.wav / source.mp4
    cand = sorted(con_dir.glob("source*"))
    for c in cand:
        if c.is_file():
            return c
    raise FileNotFoundError(f"No source* file in contribution dir: {con_dir}")


def resolve_input_contribution(
    *,
    session_id: str,
    layout: HasContributions,
    contribution_id: Optional[str] = None,
) -> ResolvedInput:
    """Resolve which contribution should be processed for a run.

    Rule:
    - If contribution_id is provided -> validate and return it.
    - Else -> pick the latest contribution for session by created_ts in contribution.json.
    """
    if contribution_id:
        con_dir = layout.contributions / contribution_id
        if not con_dir.exists():
            raise FileNotFoundError(f"contribution_id not found: {contribution_id}")
        meta = _load_manifest(con_dir)
        src = _find_source_file(con_dir)
        return ResolvedInput(
            contribution_id=contribution_id,
            source_path=src,
            source_kind=str(meta.get("source_kind", "")),
        )

    latest: Tuple[float, str, Path, str] | None = None
    for con_dir in layout.contributions.iterdir():
        if not con_dir.is_dir():
            continue
        try:
            meta = _load_manifest(con_dir)
            if meta.get("session_id") != session_id:
                continue
            created = float(meta.get("created_ts", 0.0))
            src = _find_source_file(con_dir)
            kind = str(meta.get("source_kind", ""))
            if latest is None or created > latest[0]:
                latest = (created, con_dir.name, src, kind)
        except Exception:
            continue

    if latest is None:
        raise FileNotFoundError(f"no contributions found for session_id: {session_id}")

    _, cid, src, kind = latest
    return ResolvedInput(contribution_id=cid, source_path=src, source_kind=kind)
