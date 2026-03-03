from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import load_manifest
from ashby.modules.meetings.session_state import load_session_state, get_speaker_overlay_for_transcript
from ashby.modules.meetings.overlays import load_speaker_map_overlay
from ashby.modules.meetings.transcript_versions import load_transcript_version

from .sqlite_fts import connect, ensure_schema, get_db_path, normalize_person_name


_SPEAKER_RE = re.compile(r"^(SPEAKER_\d+):\s*(.*)$")


@dataclass(frozen=True)
class Segment:
    session_id: str
    run_id: str
    segment_id: int
    speaker_label: Optional[str]
    start_ms: Optional[int]
    end_ms: Optional[int]
    t_start: Optional[float]
    t_end: Optional[float]
    text: str
    source_path: str


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_segments_from_transcript_json(path: Path, *, session_id: str, run_id: str) -> Iterable[Segment]:
    """Parse transcript.json or aligned_transcript.json (v1) into deterministic segments.

    Contract:
    - segment_id is the stable anchor (0-based, deterministic)
    - timestamps are stored as start_ms/end_ms (ms)
    - speaker label stored as speaker (string)
    """
    payload = _load_json(path)
    segs = payload.get("segments")
    if not isinstance(segs, list):
        raise ValueError(f"Transcript JSON missing segments list: {path}")

    for seg in segs:
        if not isinstance(seg, dict):
            continue

        try:
            segment_id = int(seg.get("segment_id"))
        except Exception:
            continue

        text = str(seg.get("text") or "").strip()
        if not text:
            continue

        sp = seg.get("speaker")
        speaker_label = sp.strip().upper() if isinstance(sp, str) and sp.strip() else None

        start_ms: Optional[int]
        end_ms: Optional[int]
        try:
            start_ms = int(seg.get("start_ms")) if seg.get("start_ms") is not None else None
        except Exception:
            start_ms = None
        try:
            end_ms = int(seg.get("end_ms")) if seg.get("end_ms") is not None else None
        except Exception:
            end_ms = None

        # Derive seconds for backward compatibility in FTS / search output.
        # Treat (0,0) as unknown.
        t_start: Optional[float] = None
        t_end: Optional[float] = None
        if start_ms is not None and end_ms is not None and (start_ms > 0 or end_ms > 0):
            t_start = float(max(0, start_ms)) / 1000.0
            t_end = float(max(max(0, start_ms), max(0, end_ms))) / 1000.0

        yield Segment(
            session_id=session_id,
            run_id=run_id,
            segment_id=segment_id,
            speaker_label=speaker_label,
            start_ms=start_ms,
            end_ms=end_ms,
            t_start=t_start,
            t_end=t_end,
            text=text,
            source_path=str(path),
        )


def _iter_segments_from_transcript_txt(path: Path, *, session_id: str, run_id: str) -> Iterable[Segment]:
    """Parse transcript.txt into deterministic segments.

    V1 (QUEST_022) uses transcript line numbers as citation anchors.
    We only index SPEAKER_* lines.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_no, raw in enumerate(lines, start=1):
        s = raw.strip()
        if not s:
            continue

        m = _SPEAKER_RE.match(s)
        if not m:
            # ignore headers / non-speaker lines
            continue

        speaker = m.group(1).strip().upper()
        text = m.group(2).strip()
        if not text:
            continue

        yield Segment(
            session_id=session_id,
            run_id=run_id,
            segment_id=int(line_no),  # deterministic: transcript line anchor
            speaker_label=speaker,
            start_ms=None,
            end_ms=None,
            t_start=None,
            t_end=None,
            text=text,
            source_path=str(path),
        )


def _detect_transcript_source(run_dir: Path, run_state: Dict[str, Any]) -> Optional[Path]:
    """Resolve transcript source for ingestion.

    Preference (QUEST_057):
    1) aligned_transcript.json (if present)
    2) transcript.json
    3) transcript.txt (legacy fallback)

    We prefer aligned transcript because it can carry diarization speaker labels.
    """
    # 1) explicit artifact pointer in run.json
    arts = run_state.get("artifacts") if isinstance(run_state, dict) else None
    if isinstance(arts, list):
        for a in arts:
            if not isinstance(a, dict):
                continue
            if a.get("kind") == "aligned_transcript" and isinstance(a.get("path"), str):
                p = Path(a["path"])
                if p.exists():
                    return p
        for a in arts:
            if not isinstance(a, dict):
                continue
            if a.get("kind") == "transcript":
                # Adapter may provide json_path.
                jp = a.get("json_path")
                if isinstance(jp, str):
                    p = Path(jp)
                    if p.exists():
                        return p
                # If only transcript.txt path is present, try sibling transcript.json.
                tp = a.get("path")
                if isinstance(tp, str):
                    p = Path(tp)
                    if p.exists() and p.suffix.lower() == ".txt":
                        j2 = p.with_suffix(".json")
                        if j2.exists():
                            return j2

    # 2) conventional paths
    aligned = run_dir / "artifacts" / "aligned_transcript.json"
    if aligned.exists():
        return aligned
    tjson = run_dir / "artifacts" / "transcript.json"
    if tjson.exists():
        return tjson
    ttxt = run_dir / "artifacts" / "transcript.txt"
    return ttxt if ttxt.exists() else None


def ingest_run(run_id: str, *, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Ingest one run's transcript into SQLite FTS.

    Determinism rules:
    - Never mutate transcripts.
    - Idempotent per (session_id, run_id): delete-then-insert.
    - Store enough pointers to reconstruct citations (segment_id + source_path).
    """
    lay = init_stuart_root()
    run_dir = lay.runs / run_id
    run_json = run_dir / "run.json"
    if not run_json.exists():
        raise FileNotFoundError(f"Unknown run_id (missing manifest): {run_json}")

    run_state = load_manifest(run_json)
    session_id = run_state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError(f"Run manifest missing session_id: {run_json}")

    sess_json = lay.sessions / session_id / "session.json"
    if not sess_json.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {sess_json}")
    sess = load_manifest(sess_json)

    transcript_path = _detect_transcript_source(run_dir, run_state)
    if transcript_path is None:
        raise FileNotFoundError(f"No transcript artifact found for run_id={run_id}")

    if transcript_path.suffix.lower() == ".json":
        segs = list(_iter_segments_from_transcript_json(transcript_path, session_id=session_id, run_id=run_id))
    else:
        # Legacy fallback: transcript.txt
        segs = list(_iter_segments_from_transcript_txt(transcript_path, session_id=session_id, run_id=run_id))
    if not segs:
        raise ValueError(f"Transcript had no indexable segments: {transcript_path}")

    if db_path is None:
        db_path = get_db_path(stuart_root=lay.root)

    conn = connect(db_path)
    try:
        ensure_schema(conn)

        # Upsert session + run metadata
        conn.execute(
            "INSERT OR REPLACE INTO sessions(session_id, created_ts, mode, title) VALUES(?, ?, ?, ?);",
            (
                session_id,
                float(sess.get("created_ts")) if sess.get("created_ts") is not None else None,
                sess.get("mode"),
                sess.get("title"),
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, session_id, created_ts, status) VALUES(?, ?, ?, ?);",
            (
                run_id,
                session_id,
                float(run_state.get("created_ts")) if run_state.get("created_ts") is not None else None,
                run_state.get("status"),
            ),
        )

        
        # Speaker map snapshot (QUEST_060): label -> name mappings (user-provided overlays only).
        # Idempotent per (session_id, run_id): delete-then-insert.
        conn.execute("DELETE FROM speaker_maps WHERE session_id = ? AND run_id = ?;", (session_id, run_id))

        overlay_id = None
        mapping: Dict[str, str] = {}

        # Prefer overlay snapshot recorded in this run's manifest (QUEST_068).
        arts = run_state.get("artifacts") if isinstance(run_state, dict) else None
        if isinstance(arts, list):
            for a in reversed(arts):
                if not isinstance(a, dict):
                    continue
                if a.get("kind") != "speaker_map_overlay":
                    continue

                oid = a.get("overlay_id")
                if isinstance(oid, str) and oid.strip():
                    overlay_id = oid.strip()

                mraw = a.get("mapping")
                if isinstance(mraw, dict) and mraw:
                    for k, v in mraw.items():
                        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                            mapping[k.strip().upper()] = v.strip()
                break

        # Fallback: active session overlay (legacy behavior; pre-QUEST_068 runs).
        if overlay_id is None:
            try:
                st = load_session_state(session_id)
                ovr = st.get("active_speaker_overlay_id")
                if isinstance(ovr, str) and ovr.strip():
                    overlay_id = ovr.strip()
                    mapping = load_speaker_map_overlay(session_id, overlay_id)
            except Exception:
                overlay_id = overlay_id or None
                mapping = {}

        # If we have an overlay_id but no mapping embedded, load from the overlay artifact.
        if overlay_id is not None and not mapping:
            try:
                mapping = load_speaker_map_overlay(session_id, overlay_id)
            except Exception:
                mapping = {}

        map_rows: List[Tuple[Any, ...]] = []
        if mapping:
            created_ts = float(run_state.get("created_ts")) if run_state.get("created_ts") is not None else None
            for k, v in mapping.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    continue
                speaker_label = k.strip().upper()
                speaker_name = v.strip()
                if not speaker_label or not speaker_name:
                    continue
                speaker_name_norm = normalize_person_name(speaker_name)
                if not speaker_name_norm:
                    continue
                map_rows.append((session_id, run_id, speaker_label, speaker_name, speaker_name_norm, overlay_id, created_ts))

        if map_rows:
            conn.executemany(
                """
                INSERT INTO speaker_maps(
                  session_id, run_id, speaker_label,
                  speaker_name, speaker_name_norm,
                  overlay_id, created_ts
                ) VALUES(?, ?, ?, ?, ?, ?, ?);
                """,
                map_rows,
            )

        # Idempotent ingestion: replace segments for this run
        conn.execute("DELETE FROM segments WHERE session_id = ? AND run_id = ?;", (session_id, run_id))
        conn.execute("DELETE FROM segments_fts WHERE session_id = ? AND run_id = ?;", (session_id, run_id))

        title = sess.get("title")
        mode = sess.get("mode")

        rows_segments: List[Tuple[Any, ...]] = []
        rows_fts: List[Tuple[Any, ...]] = []
        for s in segs:
            rows_segments.append(
                (
                    s.session_id,
                    s.run_id,
                    int(s.segment_id),
                    s.speaker_label,
                    s.start_ms,
                    s.end_ms,
                    s.t_start,
                    s.t_end,
                    s.text,
                    s.source_path,
                )
            )
            rows_fts.append(
                (
                    s.text,
                    s.session_id,
                    s.run_id,
                    int(s.segment_id),
                    s.speaker_label,
                    s.t_start,
                    s.t_end,
                    title,
                    mode,
                )
            )

        conn.executemany(
            """
            INSERT INTO segments(
              session_id, run_id, segment_id,
              speaker_label, start_ms, end_ms,
              t_start, t_end,
              text, source_path
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            rows_segments,
        )

        conn.executemany(
            """
            INSERT INTO segments_fts(
              text, session_id, run_id, segment_id,
              speaker_label, t_start, t_end, title, mode
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            rows_fts,
        )

        conn.commit()
        return {
            "db_path": str(db_path),
            "session_id": session_id,
            "run_id": run_id,
            "segments_indexed": len(segs),
            "transcript_path": str(transcript_path),
        }
    finally:
        conn.close()


def refresh_speaker_maps_for_transcript(
    *, session_id: str, transcript_version_id: str, db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Refresh indexed speaker map rows for one transcript version's run.

    Idempotent:
    - Deletes existing speaker_maps rows for (session_id, run_id).
    - Re-inserts rows from the transcript-scoped active overlay pointer, if present.
    """
    payload = load_transcript_version(session_id, transcript_version_id)
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("transcript version missing run_id")

    overlay_id = get_speaker_overlay_for_transcript(session_id, transcript_version_id)
    mapping: Dict[str, str] = {}
    if isinstance(overlay_id, str) and overlay_id.strip():
        mapping = load_speaker_map_overlay(session_id, overlay_id.strip())
        overlay_id = overlay_id.strip()
    else:
        overlay_id = None

    lay = init_stuart_root()
    if db_path is None:
        db_path = get_db_path(stuart_root=lay.root)

    conn = connect(db_path)
    try:
        ensure_schema(conn)
        session_manifest_path = lay.sessions / session_id / "session.json"
        session_payload: Dict[str, Any] = {}
        if session_manifest_path.exists():
            try:
                session_payload = load_manifest(session_manifest_path)
            except Exception:
                session_payload = {}

        conn.execute(
            "INSERT OR REPLACE INTO sessions(session_id, created_ts, mode, title) VALUES(?, ?, ?, ?);",
            (
                session_id,
                float(session_payload.get("created_ts")) if session_payload.get("created_ts") is not None else None,
                session_payload.get("mode"),
                session_payload.get("title"),
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, session_id, created_ts, status) VALUES(?, ?, ?, ?);",
            (
                run_id,
                session_id,
                float(payload.get("created_ts")) if payload.get("created_ts") is not None else None,
                "succeeded",
            ),
        )
        conn.execute("DELETE FROM speaker_maps WHERE session_id = ? AND run_id = ?;", (session_id, run_id))

        rows: List[Tuple[Any, ...]] = []
        created_ts = float(payload.get("created_ts")) if payload.get("created_ts") is not None else None
        for key, value in (mapping or {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            speaker_label = key.strip().upper()
            speaker_name = value.strip()
            if not speaker_label or not speaker_name:
                continue
            speaker_name_norm = normalize_person_name(speaker_name)
            if not speaker_name_norm:
                continue
            rows.append((session_id, run_id, speaker_label, speaker_name, speaker_name_norm, overlay_id, created_ts))

        if rows:
            conn.executemany(
                """
                INSERT INTO speaker_maps(
                  session_id, run_id, speaker_label,
                  speaker_name, speaker_name_norm,
                  overlay_id, created_ts
                ) VALUES(?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
        conn.commit()
        return {
            "session_id": session_id,
            "transcript_version_id": transcript_version_id,
            "run_id": run_id,
            "overlay_id": overlay_id,
            "rows_inserted": len(rows),
            "db_path": str(db_path),
        }
    finally:
        conn.close()
