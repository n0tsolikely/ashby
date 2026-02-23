from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashby.modules.meetings.formalize.journal_json import formalize_journal_to_journal_json


def _write_aligned_transcript(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "I went to the store."},
            {"segment_id": 1, "start_ms": 1000, "end_ms": 2000, "speaker": "SPEAKER_00", "text": "I felt good about it."},
        ],
        "engine": "test",
    }
    (artifacts / "aligned_transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_formalize_journal_local_only_fallback(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run_001"
    _write_aligned_transcript(run_dir)

    monkeypatch.delenv("ASHBY_EXECUTION_PROFILE", raising=False)
    monkeypatch.delenv("ASHBY_MEETINGS_LLM_ENABLED", raising=False)

    art = formalize_journal_to_journal_json(run_dir, template_id="default", retention="MED")
    assert art["kind"] == "journal_json"

    out_path = run_dir / "artifacts" / "journal.json"
    assert out_path.exists()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["session_id"] == "ses_test"
    assert payload["run_id"] == "run_001"
    assert payload["header"]["mode"] == "journal"

    # deterministic fallback must not invent action items
    assert payload["action_items"] == []

    # narrative section should be transcript-backed and cited
    assert payload["narrative_sections"]
    cites = payload["narrative_sections"][0].get("citations") or []
    assert cites and cites[0]["segment_id"] == 0


def test_formalize_journal_hybrid_uses_llm_when_enabled(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run_002"
    _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "HYBRID")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    from ashby.modules.meetings.formalize import journal_json as mod

    def fake_call_openai_journal_json(*, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "version": 1,
            "session_id": "ses_test",
            "run_id": "run_002",
            "header": {"title": "T", "mode": "journal", "retention": "MED", "template_id": "default"},
            "narrative_sections": [{"section_id": "sec_001", "title": "Day", "text": "I went to the store."}],
            "key_points": [{"point_id": "kp_001", "text": "Went to the store", "citations": [{"segment_id": 0}]}],
            "action_items": [{"action_id": "act_001", "text": "Buy milk", "assignee": None, "due_date": None, "citations": [{"segment_id": 0}]}],
            "feelings": [],
            "mood": "",
        }
        return json.dumps(payload)

    monkeypatch.setattr(mod, "_call_openai_journal_json", fake_call_openai_journal_json)

    art = formalize_journal_to_journal_json(run_dir, template_id="default", retention="MED")
    assert art["kind"] == "journal_json"

    payload = json.loads((run_dir / "artifacts" / "journal.json").read_text(encoding="utf-8"))
    assert payload["key_points"][0]["citations"][0]["segment_id"] == 0
    assert payload["action_items"][0]["citations"][0]["segment_id"] == 0


def test_formalize_journal_hybrid_invalid_json_fails_loud(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run_003"
    _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "HYBRID")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    from ashby.modules.meetings.formalize import journal_json as mod
    monkeypatch.setattr(mod, "_call_openai_journal_json", lambda **kwargs: "NOT JSON")

    with pytest.raises(ValueError):
        formalize_journal_to_journal_json(run_dir, template_id="default", retention="MED")

    assert (run_dir / "artifacts" / "journal_llm_raw.txt").exists()
    assert (run_dir / "artifacts" / "journal_llm_failure.json").exists()
