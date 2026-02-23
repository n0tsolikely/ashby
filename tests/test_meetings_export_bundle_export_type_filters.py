from __future__ import annotations

import json
import zipfile

from pathlib import Path

from ashby.modules.meetings.export.bundle import export_session_bundle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_export_session_bundle_filters_by_export_type(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    sid = "ses_test"
    rid = "run_test"

    _write_json(root / "sessions" / sid / "session.json", {"session_id": sid, "created_ts": 1, "mode": "meeting"})
    _write_json(root / "sessions" / sid / "session_state.json", {"session_id": sid, "updated_ts": 1})
    _write_json(root / "sessions" / sid / "transcripts" / "index.jsonl", {"dummy": True})
    _write_json(root / "sessions" / sid / "transcripts" / "versions" / "trv_1.json", {"dummy": True})
    _write_json(root / "contributions" / "con_test" / "contribution.json", {"contribution_id": "con_test", "session_id": sid})
    (root / "contributions" / "con_test" / "source.wav").write_bytes(b"wav")

    _write_json(root / "runs" / rid / "run.json", {"run_id": rid, "session_id": sid, "created_ts": 1})
    (root / "runs" / rid / "events.jsonl").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "runs" / rid / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "runs" / rid / "exports").mkdir(parents=True, exist_ok=True)
    (root / "runs" / rid / "inputs" / "resolved_input.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "transcript.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "aligned_transcript.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "diarization.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "minutes.md").write_text("# minutes", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "minutes.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "evidence_map.json").write_text("{}", encoding="utf-8")
    (root / "runs" / rid / "exports" / "minutes.pdf").write_bytes(b"%PDF-1.4")

    full = export_session_bundle(sid, export_type="full_bundle")
    trn = export_session_bundle(sid, export_type="transcript_only")
    frm = export_session_bundle(sid, export_type="formalization_only")

    with zipfile.ZipFile(full.zip_path) as z:
        full_names = set(z.namelist())
    with zipfile.ZipFile(trn.zip_path) as z:
        trn_names = set(z.namelist())
    with zipfile.ZipFile(frm.zip_path) as z:
        frm_names = set(z.namelist())

    assert "runs/run_test/artifacts/transcript.json" in full_names
    assert "runs/run_test/artifacts/minutes.md" in full_names

    assert "runs/run_test/artifacts/transcript.json" in trn_names
    assert f"sessions/{sid}/transcripts/index.jsonl" in trn_names
    assert "runs/run_test/artifacts/minutes.md" not in trn_names

    assert "runs/run_test/artifacts/minutes.md" in frm_names
    assert "runs/run_test/artifacts/transcript.json" not in frm_names
    assert f"sessions/{sid}/transcripts/index.jsonl" in frm_names
