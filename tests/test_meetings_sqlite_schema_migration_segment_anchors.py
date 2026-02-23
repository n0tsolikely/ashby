from __future__ import annotations

import sqlite3
from pathlib import Path

from ashby.modules.meetings.index.sqlite_fts import connect, ensure_schema


def _create_v1_db(path: Path) -> None:
    """Create a minimal v1 SQLite index to validate additive migrations.

    v1 characteristics:
    - segments table has t_start/t_end but no start_ms/end_ms
    - schema_version stored in meta
    """
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )
    cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', '1');")

    cur.execute(
        """
        CREATE TABLE sessions (
          session_id TEXT PRIMARY KEY,
          created_ts REAL,
          mode TEXT,
          title TEXT
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE runs (
          run_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          created_ts REAL,
          status TEXT,
          FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE segments (
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

    cur.execute(
        """
        CREATE VIRTUAL TABLE segments_fts
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

    # Seed one row.
    cur.execute(
        "INSERT INTO sessions(session_id, created_ts, mode, title) VALUES(?, ?, ?, ?);",
        ("sess_1", None, "meeting", "A"),
    )
    cur.execute(
        "INSERT INTO runs(run_id, session_id, created_ts, status) VALUES(?, ?, ?, ?);",
        ("run_1", "sess_1", None, "DONE"),
    )
    cur.execute(
        """
        INSERT INTO segments(
          session_id, run_id, segment_id,
          speaker_label, t_start, t_end,
          text, source_path
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?);
        """,
        ("sess_1", "run_1", 1, "SPEAKER_00", None, None, "hello world", "/tmp/transcript.txt"),
    )
    cur.execute(
        """
        INSERT INTO segments_fts(
          text, session_id, run_id, segment_id,
          speaker_label, t_start, t_end, title, mode
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        ("hello world", "sess_1", "run_1", 1, "SPEAKER_00", None, None, "A", "meeting"),
    )

    conn.commit()
    conn.close()


def test_sqlite_schema_migration_adds_segment_anchor_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "stuart_index_v1.sqlite3"
    _create_v1_db(db_path)

    conn = connect(db_path)
    try:
        # Should migrate cleanly (no deletes).
        ensure_schema(conn)

        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(segments);").fetchall()}
        assert "start_ms" in cols
        assert "end_ms" in cols

        # Row should still exist, new columns should be queryable.
        row = conn.execute(
            "SELECT start_ms, end_ms FROM segments WHERE session_id=? AND run_id=? AND segment_id=?;",
            ("sess_1", "run_1", 1),
        ).fetchone()
        assert row is not None
        assert row[0] is None and row[1] is None

        conn.execute(
            "UPDATE segments SET start_ms=?, end_ms=? WHERE session_id=? AND run_id=? AND segment_id=?;",
            (123, 456, "sess_1", "run_1", 1),
        )
        conn.commit()

        row2 = conn.execute(
            "SELECT start_ms, end_ms FROM segments WHERE session_id=? AND run_id=? AND segment_id=?;",
            ("sess_1", "run_1", 1),
        ).fetchone()
        assert row2[0] == 123 and row2[1] == 456

        # Meta should be bumped to current version.
        v = conn.execute("SELECT value FROM meta WHERE key='schema_version';").fetchone()[0]
        assert int(v) >= 2

        # Idempotent on repeat.
        ensure_schema(conn)
    finally:
        conn.close()
