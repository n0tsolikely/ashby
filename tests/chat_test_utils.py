from __future__ import annotations

from pathlib import Path

from ashby.modules.meetings.index.sqlite_fts import connect, ensure_schema, get_db_path


def seed_chat_index(root: Path) -> None:
    db = get_db_path(stuart_root=root)
    conn = connect(db)
    ensure_schema(conn)

    conn.execute("INSERT INTO sessions(session_id, created_ts, mode, title) VALUES(?,?,?,?)", ("ses_a", 1.0, "meeting", "Alpha Session"))
    conn.execute("INSERT INTO sessions(session_id, created_ts, mode, title) VALUES(?,?,?,?)", ("ses_b", 2.0, "meeting", "Beta Session"))
    conn.execute("INSERT INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?)", ("run_a", "ses_a", 1.0, "succeeded"))
    conn.execute("INSERT INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?)", ("run_b", "ses_b", 2.0, "succeeded"))

    rows = [
        ("ses_a", "run_a", 1, "SPEAKER_00", 0, 2000, 0.0, 2.0, "alpha contains roadmap", "runs/run_a/artifacts/transcript.json", "Alpha Session"),
        ("ses_b", "run_b", 2, "SPEAKER_01", 3000, 6000, 3.0, 6.0, "beta contains budget", "runs/run_b/artifacts/transcript.json", "Beta Session"),
    ]
    for sid, rid, seg, spk, sm, em, ts, te, txt, src, title in rows:
        conn.execute(
            "INSERT INTO segments(session_id, run_id, segment_id, speaker_label, start_ms, end_ms, t_start, t_end, text, source_path) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (sid, rid, seg, spk, sm, em, ts, te, txt, src),
        )
        conn.execute(
            "INSERT INTO segments_fts(text, session_id, run_id, segment_id, speaker_label, t_start, t_end, title, mode) VALUES(?,?,?,?,?,?,?,?,?)",
            (txt, sid, rid, seg, spk, ts, te, title, "meeting"),
        )

    conn.execute(
        "INSERT INTO speaker_maps(session_id, run_id, speaker_label, speaker_name, speaker_name_norm, overlay_id, created_ts) VALUES(?,?,?,?,?,?,?)",
        ("ses_a", "run_a", "SPEAKER_00", "Alice", "alice", "ov_1", 1.0),
    )

    conn.commit()
    conn.close()
