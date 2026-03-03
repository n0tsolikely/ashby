from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.formalize.journal_json import formalize_journal_to_journal_json
from ashby.modules.meetings.formalize.minutes_json import formalize_meeting_to_minutes_json


def _write_aligned(run_dir: Path, *, session_id: str) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": session_id,
        "run_id": run_dir.name,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1200, "speaker": "SPEAKER_00", "text": "Template title coverage."},
        ],
        "engine": "test",
    }
    (artifacts / "aligned_transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_minutes_output_includes_template_title(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_minutes"
    _write_aligned(run_dir, session_id="ses_minutes")
    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "LOCAL_ONLY")
    monkeypatch.delenv("ASHBY_MEETINGS_LLM_ENABLED", raising=False)

    formalize_meeting_to_minutes_json(run_dir, template_id="default", template_version="2", retention="MED")
    out = json.loads((run_dir / "artifacts" / "minutes.json").read_text(encoding="utf-8"))
    assert out["template_id"] == "default"
    assert out["template_version"] == "2"
    assert out["template_title"] == "default"


def test_journal_output_includes_template_title(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_journal"
    _write_aligned(run_dir, session_id="ses_journal")
    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "LOCAL_ONLY")
    monkeypatch.delenv("ASHBY_MEETINGS_LLM_ENABLED", raising=False)

    formalize_journal_to_journal_json(run_dir, template_id="default", template_version="2", retention="MED")
    out = json.loads((run_dir / "artifacts" / "journal.json").read_text(encoding="utf-8"))
    assert out["template_id"] == "default"
    assert out["template_version"] == "2"
    assert out["template_title"] == "default"
