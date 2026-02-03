from ashby.modules.meetings.store import create_session, create_run
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.index import ingest_run, connect, get_db_path, search


def test_sqlite_fts_ingest_and_search_is_deterministic(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    # Session + Run A
    session_a = create_session(mode="meeting", title="A")
    run_a = create_run(session_id=session_a, plan={"steps": []})
    lay = init_stuart_root()
    transcribe_stub(lay.runs / run_a)

    r1 = ingest_run(run_a)
    db_path = get_db_path(stuart_root=lay.root)
    assert r1["db_path"] == str(db_path)
    assert db_path.exists()

    conn = connect(db_path)
    try:
        hits = search(conn, "Second line")
        assert hits, "Expected keyword hits from transcript"
        assert any(h.run_id == run_a for h in hits)
    finally:
        conn.close()

    # Rerun ingestion should not duplicate rows
    r2 = ingest_run(run_a)
    assert r2["segments_indexed"] == r1["segments_indexed"]

    conn = connect(db_path)
    try:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM segments WHERE session_id=? AND run_id=?;",
            (session_a, run_a),
        ).fetchone()[0]
        assert n == r1["segments_indexed"]
    finally:
        conn.close()

    # Session + Run B (no collisions)
    session_b = create_session(mode="meeting", title="B")
    run_b = create_run(session_id=session_b, plan={"steps": []})
    lay2 = init_stuart_root()
    transcribe_stub(lay2.runs / run_b)
    ingest_run(run_b)

    conn2 = connect(db_path)
    try:
        hits2 = search(conn2, "sample speaker")
        run_ids = {h.run_id for h in hits2}
        assert run_a in run_ids and run_b in run_ids

        na = conn2.execute("SELECT COUNT(*) FROM segments WHERE run_id=?;", (run_a,)).fetchone()[0]
        nb = conn2.execute("SELECT COUNT(*) FROM segments WHERE run_id=?;", (run_b,)).fetchone()[0]
        assert na > 0 and nb > 0
    finally:
        conn2.close()
