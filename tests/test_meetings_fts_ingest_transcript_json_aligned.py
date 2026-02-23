from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.index import connect, get_db_path, ingest_run, search
from ashby.modules.meetings.store import create_run, create_session


def _dump_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_ingest_prefers_aligned_transcript_json_and_stores_anchors(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="T")
    run_id = create_run(session_id=ses, plan={"steps": []})

    lay = init_stuart_root()
    run_dir = lay.runs / run_id
    artifacts = run_dir / "artifacts"
    tjson = artifacts / "transcript.json"
    ajson = artifacts / "aligned_transcript.json"

    # Base transcript: speaker=00
    _dump_json(
        tjson,
        {
            "version": 1,
            "session_id": ses,
            "run_id": run_id,
            "segments": [
                {
                    "segment_id": 0,
                    "start_ms": 1000,
                    "end_ms": 2500,
                    "speaker": "SPEAKER_00",
                    "text": "hello world",
                },
                {
                    "segment_id": 1,
                    "start_ms": 3000,
                    "end_ms": 4000,
                    "speaker": "SPEAKER_00",
                    "text": "second segment",
                },
            ],
            "engine": "test",
        },
    )

    # Aligned transcript overrides speaker labels; ingest should prefer this when present.
    _dump_json(
        ajson,
        {
            "version": 1,
            "session_id": ses,
            "run_id": run_id,
            "segments": [
                {
                    "segment_id": 0,
                    "start_ms": 1000,
                    "end_ms": 2500,
                    "speaker": "SPEAKER_02",
                    "text": "hello world",
                    "speaker_source": "diarization",
                },
                {
                    "segment_id": 1,
                    "start_ms": 3000,
                    "end_ms": 4000,
                    "speaker": "SPEAKER_01",
                    "text": "second segment",
                    "speaker_source": "diarization",
                },
            ],
            "engine": "test",
        },
    )

    r = ingest_run(run_id)
    assert r["transcript_path"].endswith("aligned_transcript.json")

    db_path = get_db_path(stuart_root=lay.root)
    assert r["db_path"] == str(db_path)
    assert db_path.exists()

    conn = connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT speaker_label, start_ms, end_ms, t_start, t_end
            FROM segments
            WHERE run_id=? AND segment_id=?;
            """,
            (run_id, 0),
        ).fetchone()

        assert row is not None
        assert row["speaker_label"] == "SPEAKER_02"
        assert int(row["start_ms"]) == 1000
        assert int(row["end_ms"]) == 2500
        assert abs(float(row["t_start"]) - 1.0) < 1e-6
        assert abs(float(row["t_end"]) - 2.5) < 1e-6

        hits = search(conn, "hello", limit=5, session_id=ses)
        assert hits, "Expected keyword hits from transcript"
        top = hits[0]
        assert top.run_id == run_id
        assert top.segment_id == 0
        assert top.t_start is not None and top.t_end is not None
    finally:
        conn.close()
