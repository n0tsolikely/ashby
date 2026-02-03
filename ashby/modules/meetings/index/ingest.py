from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import load_manifest

from .sqlite_fts import connect, ensure_schema, get_db_path


_SPEAKER_RE = re.compile(r"^(SPEAKER_\d+):\s*(.*)$")


@dataclass(frozen=True)
class Segment:
    session_id: str
    run_id: str
    segment_id: int
    speaker_label: Optional[str]
    t_start: Optional[float]
    t_end: Optional[float]
    text: str
    source_path: str


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
            t_start=None,
            t_end=None,
            text=text,
            source_path=str(path),
        )


def _detect_transcript_path(run_dir: Path, run_state: Dict[str, Any]) -> Optional[Path]:
    """Resolve transcript artifact path.

    Preference:
    1) explicit artifact pointer in run.json (kind=transcript)
    2) conventional path: <run_dir>/artifacts/transcript.txt
    """
    arts = run_state.get("artifacts") if isinstance(run_state, dict) else None
    if isinstance(arts, list):
        for a in arts:
            if not isinstance(a, dict):
                continue
            if a.get("kind") == "transcript" and isinstance(a.get("path"), str):
                p = Path(a["path"])
                if p.exists():
                    return p

    p = run_dir / "artifacts" / "transcript.txt"
    return p if p.exists() else None


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

    transcript_path = _detect_transcript_path(run_dir, run_state)
    if transcript_path is None:
        raise FileNotFoundError(f"No transcript artifact found for run_id={run_id}")

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
              speaker_label, t_start, t_end,
              text, source_path
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?);
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
