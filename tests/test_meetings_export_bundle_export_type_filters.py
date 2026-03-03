from __future__ import annotations

import json
import zipfile

from pathlib import Path

from ashby.modules.meetings.export.bundle import export_session_bundle
from ashby.modules.meetings.transcript_versions import create_transcript_version


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_export_session_bundle_filters_by_export_type(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    sid = "ses_test"
    rid = "run_test"
    trv = "trv_test"

    _write_json(root / "sessions" / sid / "session.json", {"session_id": sid, "created_ts": 1, "mode": "meeting", "title": "Test"})
    _write_json(root / "sessions" / sid / "session_state.json", {"session_id": sid, "updated_ts": 1, "active_transcript_version_id": trv})

    _write_json(root / "contributions" / "con_test" / "contribution.json", {"contribution_id": "con_test", "session_id": sid})
    (root / "contributions" / "con_test" / "source.wav").write_bytes(b"wav")

    _write_json(
        root / "runs" / rid / "run.json",
        {
            "run_id": rid,
            "session_id": sid,
            "created_ts": 1,
            "primary_outputs": {
                "mode": "meeting",
                "md": {"path": "artifacts/minutes.md"},
                "pdf": {"path": "exports/minutes.pdf"},
                "json": {"path": "artifacts/minutes.json"},
                "evidence_map": {"path": "artifacts/evidence_map.json"},
            },
            "plan": {"steps": [{"kind": "formalize", "params": {"mode": "meeting"}}]},
        },
    )
    (root / "runs" / rid / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "runs" / rid / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "runs" / rid / "exports").mkdir(parents=True, exist_ok=True)
    (root / "runs" / rid / "artifacts" / "minutes.md").write_text("# minutes", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "minutes.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "evidence_map.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "llm_usage.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "exports" / "minutes.pdf").write_bytes(b"%PDF-1.4")

    create_transcript_version(
        session_id=sid,
        run_id=rid,
        segments=[{"segment_id": 0, "speaker": "SPEAKER_00", "start_ms": 0, "end_ms": 1000, "text": "hello"}],
        diarization_enabled=True,
        asr_engine="default",
        audio_ref={},
        created_ts=1,
    )

    full = export_session_bundle(sid, export_type="full_bundle", transcript_formats=["txt"], formalization_formats=["md"])
    trn = export_session_bundle(sid, export_type="transcript_only", transcript_formats=["txt"])
    frm = export_session_bundle(sid, export_type="formalization_only", formalization_formats=["md"])
    dev = export_session_bundle(sid, export_type="dev_bundle")

    with zipfile.ZipFile(full.zip_path) as z:
        full_names = set(z.namelist())
    with zipfile.ZipFile(trn.zip_path) as z:
        trn_names = set(z.namelist())
    with zipfile.ZipFile(frm.zip_path) as z:
        frm_names = set(z.namelist())
    with zipfile.ZipFile(dev.zip_path) as z:
        dev_names = set(z.namelist())

    assert "session.json" in full_names
    assert "audio/con_test__source.wav" in full_names
    assert any(n.startswith("transcripts/") and n.endswith("/transcript.txt") for n in full_names)
    assert f"formalizations/{rid}/minutes.md" in full_names

    assert any(n.startswith("transcripts/") and n.endswith("/transcript.txt") for n in trn_names)
    assert not any(n.startswith("formalizations/") for n in trn_names)

    assert f"formalizations/{rid}/minutes.md" in frm_names
    assert not any(n.startswith("transcripts/") for n in frm_names)

    assert f"dev/formalizations/{rid}/run.json" in dev_names
    assert f"dev/formalizations/{rid}/events.jsonl" in dev_names
    assert f"dev/formalizations/{rid}/evidence_map.json" in dev_names
    assert f"dev/formalizations/{rid}/llm_usage_receipt.json" in dev_names
    assert any(n.startswith("dev/transcripts/") and n.endswith("/transcript_version.json") for n in dev_names)
