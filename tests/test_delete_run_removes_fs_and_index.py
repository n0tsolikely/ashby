from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.delete_ops import delete_run
from ashby.modules.meetings.index import sqlite_fts
from ashby.modules.meetings.init_root import init_stuart_root


def _seed_index(stuart_root: Path, *, session_id: str, run_id: str) -> None:
    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=stuart_root))
    try:
        sqlite_fts.ensure_schema(conn)
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions(session_id, created_ts, mode, title) VALUES(?,?,?,?);",
                (session_id, 1.0, "meeting", "t"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?);",
                (run_id, session_id, 1.0, "succeeded"),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO segments(
                  session_id, run_id, segment_id, speaker_label, start_ms, end_ms, t_start, t_end, text, source_path
                ) VALUES(?,?,?,?,?,?,?,?,?,?);
                """,
                (session_id, run_id, 0, "SPEAKER_00", 0, 1000, 0.0, 1.0, "hello", "/tmp/t.json"),
            )
            conn.execute(
                "INSERT INTO segments_fts(text, session_id, run_id, segment_id, speaker_label, t_start, t_end, title, mode) VALUES(?,?,?,?,?,?,?,?,?);",
                ("hello", session_id, run_id, 0, "SPEAKER_00", 0.0, 1.0, "t", "meeting"),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO speaker_maps(
                  session_id, run_id, speaker_label, speaker_name, speaker_name_norm, overlay_id, created_ts
                ) VALUES(?,?,?,?,?,?,?);
                """,
                (session_id, run_id, "SPEAKER_00", "Alex", "alex", "ovr_1", 1.0),
            )
    finally:
        conn.close()


def test_delete_run_removes_fs_and_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    lay = init_stuart_root()

    run_id = "run_delete_1"
    session_id = "ses_delete_1"
    run_dir = lay.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": run_id, "session_id": session_id, "status": "succeeded"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _seed_index(lay.root, session_id=session_id, run_id=run_id)

    out = delete_run(run_id)
    assert out["run_id"] == run_id
    assert out["session_id"] == session_id
    assert not run_dir.exists()

    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=lay.root))
    try:
        assert conn.execute("SELECT COUNT(*) FROM runs WHERE run_id = ?;", (run_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM segments WHERE run_id = ?;", (run_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM segments_fts WHERE run_id = ?;", (run_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM speaker_maps WHERE run_id = ?;", (run_id,)).fetchone()[0] == 0
        # Session row should remain for run-only delete.
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?;", (session_id,)).fetchone()[0] == 1
    finally:
        conn.close()
