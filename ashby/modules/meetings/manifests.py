from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class SessionManifest:
    session_id: str
    created_ts: float
    mode: str  # "meeting" | "journal"
    title: Optional[str] = None
    contributions: List[str] = None
    runs: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["contributions"] = d["contributions"] or []
        d["runs"] = d["runs"] or []
        return d


@dataclass
class ContributionManifest:
    contribution_id: str
    session_id: str
    created_ts: float
    source_filename: str
    source_sha256: str
    source_kind: str  # "audio" | "video"
    derived_audio_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunManifest:
    run_id: str
    session_id: str
    created_ts: float
    plan: Dict[str, Any]
    status: str  # "queued" | "running" | "succeeded" | "failed"
    started_ts: Optional[float] = None
    ended_ts: Optional[float] = None
    progress: int = 0
    stage: str = "queued"
    errors: List[Dict[str, Any]] = None
    artifacts: List[Dict[str, Any]] = None
    primary_outputs: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["errors"] = d["errors"] or []
        d["artifacts"] = d["artifacts"] or []
        d["primary_outputs"] = d.get("primary_outputs") or {}
        return d


def save_manifest_write_once(path: Path, data: Dict[str, Any]) -> None:
    # Immutability rule: never overwrite a write-once manifest.
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite manifest: {path}")
    _write_json_atomic(path, data)


def save_manifest_atomic_overwrite(path: Path, data: Dict[str, Any]) -> None:
    """Atomic overwrite (allowed ONLY for mutable state like run.json)."""
    _write_json_atomic(path, data)


def append_event_jsonl(path: Path, event: Dict[str, Any]) -> None:
    """Append-only JSONL event log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def load_manifest(path: Path) -> Dict[str, Any]:
    return _read_json(path)
