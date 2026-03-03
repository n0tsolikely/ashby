from __future__ import annotations

import json
import zipfile
from pathlib import Path

from ashby.modules.meetings.export.bundle import export_session_bundle
from ashby.modules.meetings.transcript_versions import create_transcript_version


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_dev_bundle_includes_template_text_and_metadata(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    sid = "ses_tpl_dev"
    rid = "run_tpl_dev"
    trv = "trv_tpl_dev"

    _write_json(root / "sessions" / sid / "session.json", {"session_id": sid, "created_ts": 1, "mode": "meeting", "title": "Template Dev"})
    _write_json(root / "sessions" / sid / "session_state.json", {"session_id": sid, "updated_ts": 1, "active_transcript_version_id": trv})
    _write_json(root / "contributions" / "con_tpl" / "contribution.json", {"contribution_id": "con_tpl", "session_id": sid})
    (root / "contributions" / "con_tpl" / "source.wav").write_bytes(b"wav")

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

    (root / "runs" / rid / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "runs" / rid / "exports").mkdir(parents=True, exist_ok=True)
    (root / "runs" / rid / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "runs" / rid / "artifacts" / "minutes.md").write_text("# minutes", encoding="utf-8")
    _write_json(
        root / "runs" / rid / "artifacts" / "minutes.json",
        {
            "mode": "meeting",
            "template_id": "default",
            "template_title": "default",
            "template_version": "2",
            "retention": "MED",
        },
    )
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

    dev = export_session_bundle(sid, export_type="dev_bundle")
    with zipfile.ZipFile(dev.zip_path) as z:
        names = set(z.namelist())
        assert f"dev/templates/{rid}/default/v2/metadata.json" in names
        assert f"dev/templates/{rid}/default/v2/template.md" in names
