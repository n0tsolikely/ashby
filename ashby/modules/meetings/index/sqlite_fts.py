from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

SCHEMA_VERSION = 1


def get_db_path(*, stuart_root: Optional[Path] = None) -> Path:
    """Return the canonical SQLite index path.

    Default: <STUART_ROOT>/index/stuart_index.sqlite3
    Override: environment variable STUART_INDEX_DB (absolute or relative).

    Note: STUART_ROOT itself is resolved by ashby.modules.meetings.config.
    """
    raw = (os.environ.get("STUART_INDEX_DB") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()

    if stuart_root is None:
        from ashby.modules.meetings.init_root import get_root_path

        stuart_root = get_root_path()

    return Path(stuart_root) / "index" / "stuart_index.sqlite3"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create schema if missing.

    Design goals (QUEST_022):
    - deterministic, reproducible indexing
    - idempotent ingestion (safe reruns)
    - enough pointer data to reconstruct citations (v1 uses line anchors)
    """
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )
    cur.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?);",
        (str(SCHEMA_VERSION),),
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          session_id TEXT PRIMARY KEY,
          created_ts REAL,
          mode TEXT,
          title TEXT
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          created_ts REAL,
          status TEXT,
          FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );
        """
    )

    # Canonical pointer store (not an index): stable keys and artifact pointers.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS segments (
          session_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          segment_id INTEGER NOT NULL,
          speaker_label TEXT,
          t_start REAL,
          t_end REAL,
          text TEXT NOT NULL,
          source_path TEXT,
          PRIMARY KEY(session_id, run_id, segment_id),
          FOREIGN KEY(run_id) REFERENCES runs(run_id),
          FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );
        """
    )

    # FTS index (contentless): stores text + pointers as UNINDEXED columns.
    # bm25() works on indexed columns only (text).
    cur.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts
        USING fts5(
          text,
          session_id UNINDEXED,
          run_id UNINDEXED,
          segment_id UNINDEXED,
          speaker_label UNINDEXED,
          t_start UNINDEXED,
          t_end UNINDEXED,
          title UNINDEXED,
          mode UNINDEXED,
          tokenize = 'unicode61'
        );
        """
    )

    conn.commit()


@dataclass(frozen=True)
class SearchHit:
    session_id: str
    run_id: str
    segment_id: int
    speaker_label: Optional[str]
    score: float
    snippet: str
    title: Optional[str]
    mode: Optional[str]
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    source_path: Optional[str] = None


def search(conn: sqlite3.Connection, query: str, *, limit: int = 10, session_id: Optional[str] = None) -> List[SearchHit]:
    """Keyword search against the FTS index.

    Note: FTS5 bm25() returns a lower-is-better score.
    """
    q = (query or "").strip()
    if not q:
        return []

    rows = conn.execute(
        """
        SELECT
          segments_fts.session_id AS session_id,
          segments_fts.run_id AS run_id,
          segments_fts.segment_id AS segment_id,
          segments_fts.speaker_label AS speaker_label,
          segments_fts.title AS title,
          segments_fts.mode AS mode,
          segments_fts.t_start AS t_start,
          segments_fts.t_end AS t_end,
          segments.source_path AS source_path,
          snippet(segments_fts, 0, '[', ']', '…', 10) AS snippet,
          bm25(segments_fts) AS score
        FROM segments_fts
        LEFT JOIN segments
          ON segments.session_id = segments_fts.session_id
         AND segments.run_id = segments_fts.run_id
         AND segments.segment_id = segments_fts.segment_id
        WHERE segments_fts MATCH ?
          AND (? IS NULL OR segments_fts.session_id = ?)
        ORDER BY score ASC
        LIMIT ?;
        """,
        (q, session_id, session_id, int(limit)),
    ).fetchall()

    out: List[SearchHit] = []
    for r in rows:
        out.append(
            SearchHit(
                session_id=str(r["session_id"]),
                run_id=str(r["run_id"]),
                segment_id=int(r["segment_id"]),
                speaker_label=(str(r["speaker_label"]) if r["speaker_label"] is not None else None),
                score=float(r["score"]),
                snippet=str(r["snippet"]),
                title=(str(r["title"]) if r["title"] is not None else None),
                mode=(str(r["mode"]) if r["mode"] is not None else None),
                t_start=(float(r["t_start"]) if r["t_start"] is not None else None),
                t_end=(float(r["t_end"]) if r["t_end"] is not None else None),
                source_path=(str(r["source_path"]) if r["source_path"] is not None else None),
            )
        )

    return out
