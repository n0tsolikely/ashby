from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .hashing import sha256_file
from .ids import new_id
from .init_root import init_stuart_root
from .schemas.artifacts_v1 import dump_json, validate_transcript_version_v1
from .manifests import load_manifest


def _session_manifest_path(session_id: str) -> Path:
    lay = init_stuart_root()
    return lay.sessions / session_id / "session.json"


def _ensure_session_exists(session_id: str) -> None:
    p = _session_manifest_path(session_id)
    if not p.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {p}")


def _transcripts_root(session_id: str) -> Path:
    lay = init_stuart_root()
    return lay.sessions / session_id / "transcripts"


def _versions_dir(session_id: str) -> Path:
    return _transcripts_root(session_id) / "versions"


def _session_index_path(session_id: str) -> Path:
    return _transcripts_root(session_id) / "index.jsonl"


def _global_lookup_path() -> Path:
    lay = init_stuart_root()
    return lay.root / "transcript_versions" / "lookup.jsonl"


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, sort_keys=True, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            if isinstance(parsed, dict):
                out.append(parsed)
    return out


def _normalize_audio_ref(audio_ref: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    lay = init_stuart_root()
    data = dict(audio_ref or {})
    raw = data.get("path")

    if raw is None:
        return data

    p = Path(str(raw))
    if p.is_absolute():
        candidate = p.resolve()
        root = lay.root.resolve()
        try:
            rel = candidate.relative_to(root)
        except Exception as exc:
            raise ValueError("audio_ref.path absolute path must stay under STUART_ROOT") from exc
    else:
        rel = p

    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise ValueError("audio_ref.path must be a safe relative path under STUART_ROOT")

    data["path"] = rel.as_posix()
    return data


def _normalize_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, seg in enumerate(list(segments or [])):
        s = dict(seg or {})
        row: Dict[str, Any] = {
            "segment_id": int(s.get("segment_id", i)),
            "start_ms": int(s.get("start_ms", 0)),
            "end_ms": int(s.get("end_ms", 0)),
            "text": str(s.get("text") or ""),
        }
        speaker = s.get("speaker")
        if speaker is not None and str(speaker).strip():
            row["speaker"] = str(speaker).strip()
        confidence = s.get("confidence")
        if confidence is not None:
            row["confidence"] = float(confidence)
        out.append(row)
    return out


def ensure_transcripts_dirs(session_id: str) -> Dict[str, Path]:
    _ensure_session_exists(session_id)

    transcripts_root = _transcripts_root(session_id)
    versions_dir = _versions_dir(session_id)
    transcripts_root.mkdir(parents=True, exist_ok=True)
    versions_dir.mkdir(parents=True, exist_ok=True)

    lookup = _global_lookup_path()
    lookup.parent.mkdir(parents=True, exist_ok=True)

    return {
        "transcripts_root": transcripts_root,
        "versions_dir": versions_dir,
        "session_index": _session_index_path(session_id),
        "lookup_index": lookup,
    }


def create_transcript_version(
    session_id: str,
    run_id: str,
    segments: List[Dict[str, Any]],
    *,
    diarization_enabled: bool,
    asr_engine: str = "default",
    audio_ref: Optional[Dict[str, Any]] = None,
    created_ts: Optional[float] = None,
) -> Dict[str, Any]:
    dirs = ensure_transcripts_dirs(session_id)

    transcript_version_id = new_id("trv")
    ts = float(created_ts if created_ts is not None else time.time())
    payload: Dict[str, Any] = {
        "version": 1,
        "transcript_version_id": transcript_version_id,
        "session_id": session_id,
        "run_id": run_id,
        "created_ts": ts,
        "diarization_enabled": bool(diarization_enabled),
        "asr_engine": str(asr_engine or "default").strip() or "default",
        "audio_ref": _normalize_audio_ref(audio_ref),
        "segments": _normalize_segments(segments),
    }
    validate_transcript_version_v1(payload)

    version_path = dirs["versions_dir"] / f"{transcript_version_id}.json"
    dump_json(version_path, payload, write_once=True)

    lay = init_stuart_root()
    rel_artifact_path = version_path.resolve().relative_to(lay.root.resolve()).as_posix()
    sha = sha256_file(version_path)

    summary = {
        "transcript_version_id": transcript_version_id,
        "session_id": session_id,
        "run_id": run_id,
        "created_ts": ts,
        "diarization_enabled": bool(diarization_enabled),
        "asr_engine": payload["asr_engine"],
        "segments_count": len(payload["segments"]),
        "sha256": sha,
        "artifact_path": rel_artifact_path,
    }
    _append_jsonl(dirs["session_index"], summary)
    _append_jsonl(
        dirs["lookup_index"],
        {
            "transcript_version_id": transcript_version_id,
            "session_id": session_id,
            "run_id": run_id,
            "created_ts": ts,
        },
    )
    return payload


def _iter_run_states_for_session(session_id: str) -> List[Dict[str, Any]]:
    lay = init_stuart_root()
    out: List[Dict[str, Any]] = []
    if not lay.runs.exists():
        return out
    for run_dir in sorted(lay.runs.iterdir()):
        if not run_dir.is_dir():
            continue
        run_json = run_dir / "run.json"
        if not run_json.exists():
            continue
        try:
            st = load_manifest(run_json)
        except Exception:
            continue
        if str(st.get("session_id") or "") != session_id:
            continue
        out.append(st)
    out.sort(key=lambda r: float(r.get("created_ts") or 0.0), reverse=False)
    return out


def ensure_legacy_transcript_versions(session_id: str) -> List[str]:
    """Backfill transcript versions for sessions with legacy run transcript artifacts.

    Idempotent rails:
    - never overwrites existing transcript version artifacts
    - skips runs already represented in transcripts/index.jsonl by run_id
    """
    _ensure_session_exists(session_id)
    dirs = ensure_transcripts_dirs(session_id)
    existing = list_transcript_versions(session_id)
    run_ids_existing = {str(r.get("run_id") or "") for r in existing}

    lay = init_stuart_root()
    created_ids: List[str] = []
    for st in _iter_run_states_for_session(session_id):
        run_id = str(st.get("run_id") or "")
        if not run_id or run_id in run_ids_existing:
            continue

        run_dir = lay.runs / run_id
        artifacts = run_dir / "artifacts"
        src = artifacts / "aligned_transcript.json"
        if not src.exists():
            src = artifacts / "transcript.json"
        if not src.exists():
            continue

        try:
            payload = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            continue
        segs = payload.get("segments")
        if not isinstance(segs, list) or not segs:
            continue

        created = create_transcript_version(
            session_id=session_id,
            run_id=run_id,
            segments=segs,
            diarization_enabled=bool((artifacts / "aligned_transcript.json").exists()),
            asr_engine=str(payload.get("engine") or "default"),
            audio_ref={},
            created_ts=float(st.get("created_ts") or time.time()),
        )
        run_ids_existing.add(run_id)
        created_ids.append(str(created.get("transcript_version_id") or ""))
    return [c for c in created_ids if c]


def list_transcript_versions(session_id: str) -> List[Dict[str, Any]]:
    _ensure_session_exists(session_id)
    rows = [r for r in _read_jsonl(_session_index_path(session_id)) if r.get("session_id") == session_id]
    out: List[Dict[str, Any]] = []
    for row in rows:
        trv_id = str(row.get("transcript_version_id") or "").strip()
        if not trv_id:
            continue
        if not (_versions_dir(session_id) / f"{trv_id}.json").exists():
            continue
        out.append(row)
    out.sort(key=lambda r: float(r.get("created_ts") or 0.0), reverse=True)
    return out


def load_transcript_version(session_id: str, transcript_version_id: str) -> Dict[str, Any]:
    _ensure_session_exists(session_id)
    version_path = _versions_dir(session_id) / f"{transcript_version_id}.json"
    if not version_path.exists():
        raise FileNotFoundError(f"Unknown transcript_version_id for session {session_id}: {transcript_version_id}")
    payload = json.loads(version_path.read_text(encoding="utf-8"))
    if str(payload.get("session_id") or "") != session_id:
        raise ValueError("Transcript version session_id mismatch")
    validate_transcript_version_v1(payload)
    return payload


def resolve_transcript_version(transcript_version_id: str) -> Optional[Dict[str, Any]]:
    rows = _read_jsonl(_global_lookup_path())
    for row in reversed(rows):
        if str(row.get("transcript_version_id") or "") == transcript_version_id:
            session_id = str(row.get("session_id") or "")
            if not session_id:
                continue
            if not (_versions_dir(session_id) / f"{transcript_version_id}.json").exists():
                continue
            return {
                "transcript_version_id": transcript_version_id,
                "session_id": session_id,
                "run_id": str(row.get("run_id") or ""),
                "created_ts": row.get("created_ts"),
            }
    return None


def delete_transcript_version(session_id: str, transcript_version_id: str) -> None:
    _ensure_session_exists(session_id)
    trv = str(transcript_version_id or "").strip()
    if not trv:
        raise FileNotFoundError("transcript version not found")
    version_path = _versions_dir(session_id) / f"{trv}.json"
    if not version_path.exists():
        raise FileNotFoundError(f"Unknown transcript_version_id for session {session_id}: {trv}")
    version_path.unlink()
