from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Schema version notes
# - v1 stored segment pointers as transcript line anchors (t_start/t_end often NULL)
# - v2 adds millisecond-precision anchors (start_ms/end_ms) to support stable citations
SCHEMA_VERSION = 3
def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Return current schema version from meta table.

    - Missing meta row => version 0
    - Non-integer values => treated as 0
    """
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version' LIMIT 1;",
        ).fetchone()
    except Exception:
        return 0

    if row is None:
        return 0

    try:
        return int(row[0])
    except Exception:
        return 0


def _table_columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
        return {str(r[1]) for r in rows}
    except Exception:
        return set()


def _add_column_if_missing(conn: sqlite3.Connection, *, table: str, column: str, sql_type: str) -> None:
    cols = _table_columns(conn, table)
    if column in cols:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type};")


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


def normalize_person_name(name: str) -> str:
    """Normalize a person name for exact-match attendee queries.

    Rules:
    - lowercase
    - collapse whitespace
    - no inference beyond normalization
    """
    return " ".join((name or "").strip().lower().split())


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensure the SQLite schema exists and is migrated.

    Design goals (QUEST_022 + QUEST_056):
    - deterministic, reproducible indexing
    - idempotent ingestion (safe reruns)
    - store stable anchors for citations (segment_id + timestamps)

    Migration rules:
    - additive only (never delete existing rows)
    - idempotent (safe to call repeatedly)
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
    current_version = _get_schema_version(conn)

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
          start_ms INTEGER,
          end_ms INTEGER,
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


    # Speaker identity overlays (QUEST_060): user-provided label -> name mappings.
    # Stored as snapshots per (session_id, run_id). Never inferred from transcript text.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS speaker_maps (
          session_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          speaker_label TEXT NOT NULL,
          speaker_name TEXT NOT NULL,
          speaker_name_norm TEXT NOT NULL,
          overlay_id TEXT,
          created_ts REAL,
          PRIMARY KEY(session_id, run_id, speaker_label),
          FOREIGN KEY(run_id) REFERENCES runs(run_id),
          FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );
        """
    )

    # ---------------------------------------------------------------------
    # Migrations
    # ---------------------------------------------------------------------
    # v2: add millisecond-precision anchors for stable citations.
    if current_version < 2:
        _add_column_if_missing(conn, table="segments", column="start_ms", sql_type="INTEGER")
        _add_column_if_missing(conn, table="segments", column="end_ms", sql_type="INTEGER")

    # ---------------------------------------------------------------------
    # Indexes (safe + idempotent)
    # ---------------------------------------------------------------------
    cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_session_id ON runs(session_id);")
    # Primary key is (session_id, run_id, segment_id). Add run_id index for common queries.
    cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_run_id ON segments(run_id);")

    # Speaker maps: query by attendee name -> sessions
    cur.execute("CREATE INDEX IF NOT EXISTS idx_speaker_maps_name_session ON speaker_maps(speaker_name_norm, session_id);")

    # Persist the final schema version.
    cur.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?);",
        (str(SCHEMA_VERSION),),
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


@dataclass(frozen=True)
class LibrarySession:
    session_id: str
    created_ts: Optional[float]
    mode: Optional[str]
    title: Optional[str]
    latest_run_id: Optional[str]
    latest_run_created_ts: Optional[float] = None
    latest_run_status: Optional[str] = None


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 10,
    session_id: Optional[str] = None,
    mode: Optional[str] = None,
) -> List[SearchHit]:
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
          COALESCE(segments.t_start, segments_fts.t_start) AS t_start,
          COALESCE(segments.t_end, segments_fts.t_end) AS t_end,
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
          AND (? IS NULL OR segments_fts.mode = ?)
        ORDER BY score ASC
        LIMIT ?;
        """,
        (q, session_id, session_id, mode, mode, int(limit)),
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


def list_sessions(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    mode: Optional[str] = None,
) -> List[LibrarySession]:
    """Return sessions for the library view.

    Contract (QUEST_059):
    - returns sessions with created_ts, mode, title (if available)
    - includes latest run pointer (run_id) without requiring a full-text search

    Ordering:
    - newest sessions first (created_ts DESC)
    """
    rows = conn.execute(
        """
        SELECT
          s.session_id AS session_id,
          s.created_ts AS created_ts,
          s.mode AS mode,
          s.title AS title,
          (
            SELECT r.run_id
            FROM runs r
            WHERE r.session_id = s.session_id
            ORDER BY COALESCE(r.created_ts, 0) DESC, r.run_id DESC
            LIMIT 1
          ) AS latest_run_id,
          (
            SELECT r.created_ts
            FROM runs r
            WHERE r.session_id = s.session_id
            ORDER BY COALESCE(r.created_ts, 0) DESC, r.run_id DESC
            LIMIT 1
          ) AS latest_run_created_ts,
          (
            SELECT r.status
            FROM runs r
            WHERE r.session_id = s.session_id
            ORDER BY COALESCE(r.created_ts, 0) DESC, r.run_id DESC
            LIMIT 1
          ) AS latest_run_status
        FROM sessions s
        WHERE (? IS NULL OR s.mode = ?)
        ORDER BY COALESCE(s.created_ts, 0) DESC, s.session_id DESC
        LIMIT ?;
        """,
        (mode, mode, int(limit)),
    ).fetchall()

    out: List[LibrarySession] = []
    for r in rows:
        out.append(
            LibrarySession(
                session_id=str(r['session_id']),
                created_ts=(float(r['created_ts']) if r['created_ts'] is not None else None),
                mode=(str(r['mode']) if r['mode'] is not None else None),
                title=(str(r['title']) if r['title'] is not None else None),
                latest_run_id=(str(r['latest_run_id']) if r['latest_run_id'] is not None else None),
                latest_run_created_ts=(
                    float(r['latest_run_created_ts']) if r['latest_run_created_ts'] is not None else None
                ),
                latest_run_status=(str(r['latest_run_status']) if r['latest_run_status'] is not None else None),
            )
        )
    return out


def delete_run_rows(conn: sqlite3.Connection, run_id: str) -> dict:
    """Delete indexed rows for a run_id across all index tables."""
    rid = str(run_id or "").strip()
    if not rid:
        return {"run_id": rid, "deleted": 0}
    with conn:
        conn.execute("DELETE FROM speaker_maps WHERE run_id = ?;", (rid,))
        conn.execute("DELETE FROM segments_fts WHERE run_id = ?;", (rid,))
        conn.execute("DELETE FROM segments WHERE run_id = ?;", (rid,))
        rc = conn.execute("DELETE FROM runs WHERE run_id = ?;", (rid,)).rowcount
    return {"run_id": rid, "deleted": int(rc if rc is not None and rc > 0 else 0)}


def delete_session_rows(conn: sqlite3.Connection, session_id: str) -> dict:
    """Delete indexed rows for a session_id across all index tables."""
    sid = str(session_id or "").strip()
    if not sid:
        return {"session_id": sid, "deleted": 0}
    with conn:
        conn.execute("DELETE FROM speaker_maps WHERE session_id = ?;", (sid,))
        conn.execute("DELETE FROM segments_fts WHERE session_id = ?;", (sid,))
        conn.execute("DELETE FROM segments WHERE session_id = ?;", (sid,))
        conn.execute("DELETE FROM runs WHERE session_id = ?;", (sid,))
        rc = conn.execute("DELETE FROM sessions WHERE session_id = ?;", (sid,)).rowcount
    return {"session_id": sid, "deleted": int(rc if rc is not None and rc > 0 else 0)}


def delete_transcript_version_rows(conn: sqlite3.Connection, transcript_version_id: str, *, run_ids: Optional[List[str]] = None) -> dict:
    """Delete index rows tied to a transcript version by associated run_ids."""
    trv = str(transcript_version_id or "").strip()
    rids = [str(r).strip() for r in (run_ids or []) if str(r).strip()]
    deleted = 0
    with conn:
        for rid in rids:
            conn.execute("DELETE FROM speaker_maps WHERE run_id = ?;", (rid,))
            conn.execute("DELETE FROM segments_fts WHERE run_id = ?;", (rid,))
            conn.execute("DELETE FROM segments WHERE run_id = ?;", (rid,))
            rc = conn.execute("DELETE FROM runs WHERE run_id = ?;", (rid,)).rowcount
            deleted += int(rc if rc is not None and rc > 0 else 0)
    return {"transcript_version_id": trv, "deleted_runs": deleted}


def list_sessions_by_attendee(
    conn: sqlite3.Connection,
    attendee: str,
    *,
    limit: int = 50,
    mode: Optional[str] = None,
) -> List[LibrarySession]:
    """Return sessions where a user-provided speaker overlay maps to the attendee name.

    Contract (QUEST_060):
    - only matches speaker_maps (never transcript text)
    - exact match after normalization (case/whitespace insensitive)
    - returns sessions suitable for a library view

    Example: attendee="Greg" matches mapping SPEAKER_00 -> "Greg".
    """
    want = normalize_person_name(attendee)
    if not want:
        return []

    rows = conn.execute(
        """
        SELECT
          s.session_id AS session_id,
          s.created_ts AS created_ts,
          s.mode AS mode,
          s.title AS title,
          (
            SELECT r.run_id
            FROM runs r
            WHERE r.session_id = s.session_id
            ORDER BY COALESCE(r.created_ts, 0) DESC, r.run_id DESC
            LIMIT 1
          ) AS latest_run_id,
          (
            SELECT r.created_ts
            FROM runs r
            WHERE r.session_id = s.session_id
            ORDER BY COALESCE(r.created_ts, 0) DESC, r.run_id DESC
            LIMIT 1
          ) AS latest_run_created_ts,
          (
            SELECT r.status
            FROM runs r
            WHERE r.session_id = s.session_id
            ORDER BY COALESCE(r.created_ts, 0) DESC, r.run_id DESC
            LIMIT 1
          ) AS latest_run_status
        FROM sessions s
        WHERE (? IS NULL OR s.mode = ?)
          AND EXISTS (
            SELECT 1
            FROM speaker_maps sm
            WHERE sm.session_id = s.session_id
              AND sm.speaker_name_norm = ?
            LIMIT 1
          )
        ORDER BY COALESCE(s.created_ts, 0) DESC, s.session_id DESC
        LIMIT ?;
        """
        ,
        (mode, mode, want, int(limit)),
    ).fetchall()

    out: List[LibrarySession] = []
    for r in rows:
        out.append(
            LibrarySession(
                session_id=str(r['session_id']),
                created_ts=(float(r['created_ts']) if r['created_ts'] is not None else None),
                mode=(str(r['mode']) if r['mode'] is not None else None),
                title=(str(r['title']) if r['title'] is not None else None),
                latest_run_id=(str(r['latest_run_id']) if r['latest_run_id'] is not None else None),
                latest_run_created_ts=(
                    float(r['latest_run_created_ts']) if r['latest_run_created_ts'] is not None else None
                ),
                latest_run_status=(str(r['latest_run_status']) if r['latest_run_status'] is not None else None),
            )
        )
    return out
