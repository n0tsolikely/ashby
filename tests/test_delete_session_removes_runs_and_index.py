from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.delete_ops import delete_session
from ashby.modules.meetings.index import sqlite_fts
from ashby.modules.meetings.init_root import init_stuart_root


def _seed_session_data(stuart_root: Path) -> None:
    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=stuart_root))
    try:
        sqlite_fts.ensure_schema(conn)
        with conn:
            conn.execute("INSERT OR REPLACE INTO sessions(session_id, created_ts, mode, title) VALUES(?,?,?,?);", ("ses_a", 1.0, "meeting", "A"))
            conn.execute("INSERT OR REPLACE INTO sessions(session_id, created_ts, mode, title) VALUES(?,?,?,?);", ("ses_b", 1.0, "meeting", "B"))
            conn.execute("INSERT OR REPLACE INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?);", ("run_a1", "ses_a", 1.0, "succeeded"))
            conn.execute("INSERT OR REPLACE INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?);", ("run_a2", "ses_a", 1.0, "succeeded"))
            conn.execute("INSERT OR REPLACE INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?);", ("run_b1", "ses_b", 1.0, "succeeded"))
            for rid, sid in (("run_a1", "ses_a"), ("run_a2", "ses_a"), ("run_b1", "ses_b")):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO segments(
                      session_id, run_id, segment_id, speaker_label, start_ms, end_ms, t_start, t_end, text, source_path
                    ) VALUES(?,?,?,?,?,?,?,?,?,?);
                    """,
                    (sid, rid, 0, "SPEAKER_00", 0, 1000, 0.0, 1.0, f"text-{rid}", "/tmp/t.json"),
                )
                conn.execute(
                    "INSERT INTO segments_fts(text, session_id, run_id, segment_id, speaker_label, t_start, t_end, title, mode) VALUES(?,?,?,?,?,?,?,?,?);",
                    (f"text-{rid}", sid, rid, 0, "SPEAKER_00", 0.0, 1.0, "t", "meeting"),
                )
    finally:
        conn.close()


def test_delete_session_removes_runs_and_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    lay = init_stuart_root()

    # Session manifests
    ses_a_dir = lay.sessions / "ses_a"
    ses_a_dir.mkdir(parents=True, exist_ok=True)
    (ses_a_dir / "session.json").write_text(
        json.dumps({"session_id": "ses_a", "mode": "meeting", "title": "A"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    ses_b_dir = lay.sessions / "ses_b"
    ses_b_dir.mkdir(parents=True, exist_ok=True)
    (ses_b_dir / "session.json").write_text(
        json.dumps({"session_id": "ses_b", "mode": "meeting", "title": "B"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Run manifests
    for rid, sid in (("run_a1", "ses_a"), ("run_a2", "ses_a"), ("run_b1", "ses_b")):
        rdir = lay.runs / rid
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "run.json").write_text(
            json.dumps({"run_id": rid, "session_id": sid, "status": "succeeded"}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # Contributions and overlays
    cdir = lay.contributions / "con_a"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "contribution.json").write_text(
        json.dumps({"contribution_id": "con_a", "session_id": "ses_a"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (lay.overlays / "ses_a").mkdir(parents=True, exist_ok=True)
    (lay.overlays / "ses_b").mkdir(parents=True, exist_ok=True)

    _seed_session_data(lay.root)

    out = delete_session("ses_a")
    assert out["session_id"] == "ses_a"
    assert set(out["deleted_runs"]) == {"run_a1", "run_a2"}
    assert not (lay.sessions / "ses_a").exists()
    assert not (lay.runs / "run_a1").exists()
    assert not (lay.runs / "run_a2").exists()
    assert not (lay.contributions / "con_a").exists()
    assert not (lay.overlays / "ses_a").exists()

    # Other session must remain.
    assert (lay.sessions / "ses_b").exists()
    assert (lay.runs / "run_b1").exists()
    assert (lay.overlays / "ses_b").exists()

    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=lay.root))
    try:
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE session_id = 'ses_a';").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM runs WHERE session_id = 'ses_a';").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM segments WHERE session_id = 'ses_a';").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM segments_fts WHERE session_id = 'ses_a';").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE session_id = 'ses_b';").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM runs WHERE run_id = 'run_b1';").fetchone()[0] == 1
    finally:
        conn.close()
