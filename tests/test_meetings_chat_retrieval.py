from __future__ import annotations

from pathlib import Path

from ashby.modules.meetings.chat.retrieval import attendee_sessions, hydrate_evidence, resolve_session_ref, retrieve_hits
from ashby.modules.meetings.index.sqlite_fts import connect, ensure_schema, get_db_path


def _seed_index(root: Path) -> None:
    db = get_db_path(stuart_root=root)
    conn = connect(db)
    ensure_schema(conn)
    conn.execute("INSERT INTO sessions(session_id, created_ts, mode, title) VALUES(?,?,?,?)", ("ses_a", 1.0, "meeting", "Weekly Sync"))
    conn.execute("INSERT INTO sessions(session_id, created_ts, mode, title) VALUES(?,?,?,?)", ("ses_b", 2.0, "meeting", "Weekly Sync Product"))
    conn.execute("INSERT INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?)", ("run_a", "ses_a", 1.0, "succeeded"))
    conn.execute("INSERT INTO runs(run_id, session_id, created_ts, status) VALUES(?,?,?,?)", ("run_b", "ses_b", 2.0, "succeeded"))
    conn.execute(
        "INSERT INTO segments(session_id, run_id, segment_id, speaker_label, start_ms, end_ms, t_start, t_end, text, source_path) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("ses_a", "run_a", 1, "SPEAKER_00", 1000, 5000, 1.0, 5.0, "Alice discussed launch timeline", "runs/run_a/artifacts/transcript.json"),
    )
    conn.execute(
        "INSERT INTO segments(session_id, run_id, segment_id, speaker_label, start_ms, end_ms, t_start, t_end, text, source_path) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("ses_b", "run_b", 2, "SPEAKER_01", 6000, 9000, 6.0, 9.0, "Bob reviewed budget status", "runs/run_b/artifacts/transcript.json"),
    )
    conn.execute(
        "INSERT INTO segments_fts(text, session_id, run_id, segment_id, speaker_label, t_start, t_end, title, mode) VALUES(?,?,?,?,?,?,?,?,?)",
        ("Alice discussed launch timeline", "ses_a", "run_a", 1, "SPEAKER_00", 1.0, 5.0, "Weekly Sync", "meeting"),
    )
    conn.execute(
        "INSERT INTO segments_fts(text, session_id, run_id, segment_id, speaker_label, t_start, t_end, title, mode) VALUES(?,?,?,?,?,?,?,?,?)",
        ("Bob reviewed budget status", "ses_b", "run_b", 2, "SPEAKER_01", 6.0, 9.0, "Weekly Sync Product", "meeting"),
    )
    conn.execute(
        "INSERT INTO speaker_maps(session_id, run_id, speaker_label, speaker_name, speaker_name_norm, overlay_id, created_ts) VALUES(?,?,?,?,?,?,?)",
        ("ses_a", "run_a", "SPEAKER_00", "Alice", "alice", "ov_1", 1.0),
    )
    conn.commit()
    conn.close()


def test_chat_retrieval_hydrates_full_evidence(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    _seed_index(root)

    hits = retrieve_hits("launch", session_id="ses_a", limit=5)
    assert hits
    assert hits[0].match_kind == "MENTION_MATCH"

    evidence = hydrate_evidence(hits)
    assert evidence
    assert "launch timeline" in evidence[0].text
    assert evidence[0].session_id == "ses_a"
    assert evidence[0].segment_id == 1


def test_chat_retrieval_attendee_sessions_returns_match_kind(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    _seed_index(root)

    rows = attendee_sessions("Alice")
    assert rows
    assert rows[0]["session_id"] == "ses_a"
    assert rows[0]["match_kind"] == "ATTENDEE_MATCH"


def test_chat_retrieval_resolve_session_ref_ambiguity() -> None:
    sessions = [
        {"session_id": "ses_a", "title": "Weekly Sync"},
        {"session_id": "ses_b", "title": "Weekly Sync Product"},
    ]
    rows = resolve_session_ref("weekly", sessions)
    assert len(rows) == 2
    assert all(r.get("match_kind") == "TITLE_MATCH" for r in rows)
