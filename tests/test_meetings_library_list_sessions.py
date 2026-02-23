from __future__ import annotations

from pathlib import Path

from ashby.modules.meetings.index.sqlite_fts import connect, ensure_schema, list_sessions


def test_list_sessions_returns_latest_run_id_and_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "stuart_index.sqlite3"
    conn = connect(db_path)
    try:
        ensure_schema(conn)

        # Sessions
        conn.execute(
            "INSERT INTO sessions(session_id, created_ts, mode, title) VALUES(?, ?, ?, ?);",
            ("ses_1", 1.0, "meeting", "Alpha"),
        )
        conn.execute(
            "INSERT INTO sessions(session_id, created_ts, mode, title) VALUES(?, ?, ?, ?);",
            ("ses_2", 2.0, "journal", None),
        )
        conn.execute(
            "INSERT INTO sessions(session_id, created_ts, mode, title) VALUES(?, ?, ?, ?);",
            ("ses_3", 3.0, "meeting", "NoRunsYet"),
        )

        # Runs (latest for ses_1 should be run_b)
        conn.execute(
            "INSERT INTO runs(run_id, session_id, created_ts, status) VALUES(?, ?, ?, ?);",
            ("run_a", "ses_1", 10.0, "done"),
        )
        conn.execute(
            "INSERT INTO runs(run_id, session_id, created_ts, status) VALUES(?, ?, ?, ?);",
            ("run_b", "ses_1", 12.0, "done"),
        )
        conn.execute(
            "INSERT INTO runs(run_id, session_id, created_ts, status) VALUES(?, ?, ?, ?);",
            ("run_c", "ses_2", 11.0, "queued"),
        )

        conn.commit()

        rows = list_sessions(conn, limit=10)
        assert [r.session_id for r in rows] == ["ses_3", "ses_2", "ses_1"]

        ses_3 = rows[0]
        assert ses_3.mode == "meeting"
        assert ses_3.title == "NoRunsYet"
        assert ses_3.latest_run_id is None

        ses_2 = rows[1]
        assert ses_2.mode == "journal"
        assert ses_2.title is None
        assert ses_2.latest_run_id == "run_c"
        assert ses_2.latest_run_status == "queued"

        ses_1 = rows[2]
        assert ses_1.mode == "meeting"
        assert ses_1.title == "Alpha"
        assert ses_1.latest_run_id == "run_b"
        assert ses_1.latest_run_status == "done"

        meeting_only = list_sessions(conn, limit=10, mode="meeting")
        assert [r.session_id for r in meeting_only] == ["ses_3", "ses_1"]
    finally:
        conn.close()
