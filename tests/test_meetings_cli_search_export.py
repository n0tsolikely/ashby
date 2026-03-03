from __future__ import annotations

import json
import zipfile
from pathlib import Path

from ashby.modules.meetings.cli_stuart import cmd_export, cmd_search
from ashby.modules.meetings.export.bundle import export_session_bundle
from ashby.modules.meetings.index import ingest_run
from ashby.modules.meetings.store import create_run, create_session
from ashby.modules.meetings.transcript_versions import create_transcript_version


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _write_transcript_json(path: Path, *, text: str) -> None:
    """Write a minimal transcript.json compatible with ingest_run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "segments": [
            {
                "segment_id": 0,
                "speaker": "SPEAKER_00",
                "start_ms": 0,
                "end_ms": 500,
                "text": text,
            }
        ]
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_session_with_run(root: Path, *, mode: str, title: str, transcript_text: str) -> tuple[str, str]:
    """Create a session + run + transcript artifact deterministically."""
    # create_session/create_run use STUART_ROOT from env; caller sets it.
    session_id = create_session(mode=mode, title=title)

    plan = {
        "steps": [
            {
                "kind": "formalize",
                "params": {
                    "mode": mode,
                    "template_id": "default",
                    "retention": "MED",
                },
            }
        ]
    }
    run_id = create_run(session_id=session_id, plan=plan)

    run_dir = root / "runs" / run_id
    art_dir = run_dir / "artifacts"
    _write_transcript_json(art_dir / "transcript.json", text=transcript_text)

    # Add a couple of representative outputs so export can include them.
    (art_dir / "minutes.md").write_text("# Minutes\n\nhello", encoding="utf-8")
    (art_dir / "minutes.json").write_text("{}", encoding="utf-8")
    (art_dir / "evidence_map.json").write_text("{}", encoding="utf-8")
    (art_dir / "llm_usage.json").write_text("{}", encoding="utf-8")

    # Export surface outputs live under run_dir/exports (PDF).
    exp_dir = run_dir / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)
    pdf_name = "minutes.pdf" if mode == "meeting" else "journal.pdf"
    (exp_dir / pdf_name).write_bytes(b"%PDF-1.4\n% Stuart test stub\n")

    create_transcript_version(
        session_id=session_id,
        run_id=run_id,
        segments=[
            {
                "segment_id": 0,
                "speaker": "SPEAKER_00",
                "start_ms": 0,
                "end_ms": 500,
                "text": transcript_text,
            }
        ],
        diarization_enabled=True,
        asr_engine="default",
        audio_ref={},
        created_ts=1,
    )

    ingest_run(run_id)
    return session_id, run_id


def test_cli_search_sessions_snippets_and_citations(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses_a, _run_a = _seed_session_with_run(root, mode="meeting", title="A", transcript_text="we discussed kimchi today")
    _ses_b, _run_b = _seed_session_with_run(root, mode="meeting", title="B", transcript_text="we discussed bananas")

    out = cmd_search(NS(query="kimchi", session_id=None, mode=None, limit=10))
    assert out["ok"] is True
    assert out["query"] == "kimchi"
    assert out["total_hits"] >= 1

    sessions = out.get("sessions")
    assert isinstance(sessions, list)
    assert len(sessions) == 1

    s0 = sessions[0]
    assert s0["session_id"] == ses_a
    assert "hits" in s0 and isinstance(s0["hits"], list) and len(s0["hits"]) >= 1

    h0 = s0["hits"][0]
    assert isinstance(h0.get("snippet"), str) and h0["snippet"]
    cit = h0.get("citation")
    assert isinstance(cit, dict)
    assert cit.get("session_id") == ses_a
    assert isinstance(cit.get("run_id"), str) and cit.get("run_id")
    assert isinstance(cit.get("segment_id"), int)


def test_cli_export_produces_session_bundle_zip(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    session_id, run_id = _seed_session_with_run(root, mode="meeting", title="Export", transcript_text="kimchi")

    out = cmd_export(NS(session_id=session_id, out=None))
    assert out["ok"] is True
    zpath = Path(out["zip_path"])
    assert zpath.exists()

    with zipfile.ZipFile(zpath, "r") as z:
        names = set(z.namelist())

    assert "session.json" in names
    assert any(n.startswith("transcripts/") and n.endswith("/transcript.txt") for n in names)
    assert f"formalizations/{run_id}/minutes.pdf" in names



def test_export_bundle_is_deterministic(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    session_id, _run_id = _seed_session_with_run(root, mode="meeting", title="Determinism", transcript_text="kimchi")

    z1 = tmp_path / "bundle_a.zip"
    z2 = tmp_path / "bundle_b.zip"

    export_session_bundle(session_id, out_path=z1)
    export_session_bundle(session_id, out_path=z2)

    assert z1.read_bytes() == z2.read_bytes()
