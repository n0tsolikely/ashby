from __future__ import annotations

from pathlib import Path

from ashby.modules.meetings.index.sqlite_fts import connect, ensure_schema, get_db_path, search
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.store import create_run, create_session


def test_search_respects_session_and_mode_filters(tmp_path: Path, monkeypatch):
    """QUEST_058: ensure filters are applied so doors can scope results."""
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    # Seed two sessions in different modes, each with an indexed transcript containing 'kimchi'.
    ses_meeting = create_session(mode="meeting", title="A")
    run_meeting = create_run(session_id=ses_meeting, plan={"steps": []})

    lay = init_stuart_root()
    transcribe_stub(lay.runs / run_meeting)

    # Index meeting session
    from ashby.modules.meetings.index import ingest_run

    ingest_run(run_meeting)

    ses_journal = create_session(mode="journal", title="B")
    run_journal = create_run(session_id=ses_journal, plan={"steps": []})
    transcribe_stub(lay.runs / run_journal)
    ingest_run(run_journal)

    db_path = get_db_path(stuart_root=lay.root)
    conn = connect(db_path)
    try:
        ensure_schema(conn)

        hits_all = search(conn, "kimchi", limit=50)
        assert any(h.session_id == ses_meeting for h in hits_all)
        assert any(h.session_id == ses_journal for h in hits_all)

        hits_meeting = search(conn, "kimchi", limit=50, session_id=ses_meeting)
        assert hits_meeting and all(h.session_id == ses_meeting for h in hits_meeting)

        hits_mode = search(conn, "kimchi", limit=50, mode="journal")
        assert hits_mode and all(h.mode == "journal" for h in hits_mode)
    finally:
        conn.close()
