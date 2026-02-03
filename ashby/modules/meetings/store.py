from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from .init_root import init_stuart_root
from .ids import new_id
from .hashing import sha256_file
from .manifests import (
    SessionManifest,
    ContributionManifest,
    RunManifest,
    save_manifest_write_once,
    load_manifest,
    save_manifest_atomic_overwrite,
    append_event_jsonl,
)

def create_session(mode: str, title: Optional[str] = None) -> str:
    lay = init_stuart_root()

    # create a brand-new session (append-only). No overwrites.
    session_id = new_id("ses")
    sess_dir = lay.sessions / session_id
    sess_dir.mkdir(parents=True, exist_ok=False)

    m = SessionManifest(
        session_id=session_id,
        created_ts=time.time(),
        mode=mode,
        title=title,
        contributions=[],
        runs=[],
    )
    save_manifest_write_once(sess_dir / "session.json", m.to_dict())
    return session_id

def add_contribution(session_id: str, source_path: Path, source_kind: str) -> str:
    """
    Store a contribution immutably.

    source_kind:
      - "audio"
      - "video"

    Policy rail:
      If source_kind == "video", we store the source as-is now.
      Audio extraction happens later in the pipeline; we reserve the field
      'derived_audio_path' in the manifest for that future artifact.
    """
    lay = init_stuart_root()

    # rail: session must exist
    sess_manifest = lay.sessions / session_id / "session.json"
    if not sess_manifest.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {sess_manifest}")

    contribution_id = new_id("con")

    con_dir = lay.contributions / contribution_id
    con_dir.mkdir(parents=True, exist_ok=False)

    ext = source_path.suffix.lower() or ""
    dest = con_dir / f"source{ext}"
    if dest.exists():
        raise FileExistsError(f"Refusing to overwrite source: {dest}")

    dest.write_bytes(source_path.read_bytes())
    h = sha256_file(dest)

    m = ContributionManifest(
        contribution_id=contribution_id,
        session_id=session_id,
        created_ts=time.time(),
        source_filename=source_path.name,
        source_sha256=h,
        source_kind=source_kind,
        derived_audio_path=None,
    )
    save_manifest_write_once(con_dir / "contribution.json", m.to_dict())
    return contribution_id

def create_run(session_id: str, plan: Dict[str, Any]) -> str:
    """
    Rerun semantics rail:
    Every run gets a new run_id and new run directory.
    No overwrites.
    """
    lay = init_stuart_root()

    # rail: session must exist
    sess_manifest = lay.sessions / session_id / "session.json"
    if not sess_manifest.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {sess_manifest}")

    run_id = new_id("run")

    run_dir = lay.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    m = RunManifest(
        run_id=run_id,
        session_id=session_id,
        created_ts=time.time(),
        plan=plan,
        status="queued",
        started_ts=None,
        ended_ts=None,
        progress=0,
        stage="queued",
        errors=[],
        artifacts=[],
    )
    save_manifest_write_once(run_dir / "run.json", m.to_dict())
    # initial lifecycle event
    append_event_jsonl(run_dir / "events.jsonl", {
        "ts": time.time(),
        "run_id": run_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
    })
    return run_id

def update_run_state(
    run_id: str,
    *,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    progress: Optional[int] = None,
    started_ts: Optional[float] = None,
    ended_ts: Optional[float] = None,
    error: Optional[Dict[str, Any]] = None,
    artifact: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    lay = init_stuart_root()

    run_dir = lay.runs / run_id
    run_path = run_dir / "run.json"
    events_path = run_dir / "events.jsonl"

    if not run_path.exists():
        raise FileNotFoundError(f"Unknown run_id (missing manifest): {run_path}")

    m = load_manifest(run_path)

    # rail: session must exist (derive from run state)
    session_id = m.get("session_id")
    if not session_id:
        raise ValueError(f"Run manifest missing session_id: {run_path}")

    sess_manifest = lay.sessions / str(session_id) / "session.json"
    if not sess_manifest.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {sess_manifest}")

    if status is not None:
        m["status"] = status
    if stage is not None:
        m["stage"] = stage
    if progress is not None:
        m["progress"] = int(progress)
    if started_ts is not None:
        m["started_ts"] = started_ts
    if ended_ts is not None:
        m["ended_ts"] = ended_ts

    if error is not None:
        m.setdefault("errors", [])
        m["errors"].append(error)

    if artifact is not None:
        m.setdefault("artifacts", [])
        # de-dupe rail: prevent identical artifacts from stacking across reruns of the same run_id
        key = (artifact.get("kind"), artifact.get("path"), artifact.get("sha256"))
        existing = {(a.get("kind"), a.get("path"), a.get("sha256")) for a in m["artifacts"]}
        if key not in existing:
            # de-dupe rail: prevent identical artifacts from stacking across multiple go() runs
            key = (artifact.get("kind"), artifact.get("path"), artifact.get("sha256"))
            existing = {(a.get("kind"), a.get("path"), a.get("sha256")) for a in m.get("artifacts", [])}
            if key not in existing:
                m['artifacts'].append(artifact)

    # Write state + append event
    save_manifest_atomic_overwrite(run_path, m)

    evt = {
        "ts": time.time(),
        "run_id": run_id,
        "status": m.get("status"),
        "stage": m.get("stage"),
        "progress": m.get("progress"),
    }
    if error is not None:
        evt["error"] = error
    if artifact is not None:
        evt["artifact"] = artifact

    append_event_jsonl(events_path, evt)
    return m
def get_run_state(run_id: str) -> Dict[str, Any]:
    lay = init_stuart_root()

    run_path = (lay.runs / run_id) / "run.json"
    m = load_manifest(run_path)

    # rail: session referenced by run must exist
    session_id = m.get("session_id")
    if not session_id:
        raise ValueError(f"Run manifest missing session_id: {run_path}")

    sess_manifest = lay.sessions / session_id / "session.json"
    if not sess_manifest.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {sess_manifest}")

    return m

