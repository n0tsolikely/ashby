from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashby.modules.meetings.formalize.minutes_json import formalize_meeting_to_minutes_json


def _write_aligned_transcript(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "We should do X."},
            {"segment_id": 1, "start_ms": 1000, "end_ms": 2000, "speaker": "SPEAKER_01", "text": "Agreed."},
        ],
        "engine": "test",
    }
    (artifacts / "aligned_transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_formalize_minutes_local_only_fallback(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run_001"
    _write_aligned_transcript(run_dir)

    # default profile is LOCAL_ONLY (no env set)
    monkeypatch.delenv("ASHBY_EXECUTION_PROFILE", raising=False)
    monkeypatch.delenv("ASHBY_MEETINGS_LLM_ENABLED", raising=False)

    art = formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")
    assert art["kind"] == "minutes_json"
    out_path = run_dir / "artifacts" / "minutes.json"
    assert out_path.exists()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["session_id"] == "ses_test"
    assert payload["run_id"] == "run_001"

    # deterministic fallback must not invent decisions/actions
    assert payload["decisions"] == []
    assert payload["action_items"] == []

    # notes must include citations to segment anchors
    assert payload["notes"]
    assert payload["notes"][0]["citations"][0]["segment_id"] == 0


def test_formalize_minutes_hybrid_uses_llm_when_enabled(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run_002"
    _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "HYBRID")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    # Mock remote call
    from ashby.modules.meetings.formalize import minutes_json as mod

    def fake_call_openai_minutes_json(*, system_prompt: str, user_prompt: str) -> str:
        # Return a minimal valid minutes.json payload with required keys and citations.
        payload = {
            "version": 1,
            "session_id": "ses_test",
            "run_id": "run_002",
            "header": {"title": "T", "mode": "meeting", "retention": "MED", "template_id": "default"},
            "participants": [{"speaker_label": "SPEAKER_00"}, {"speaker_label": "SPEAKER_01"}],
            "topics": [{"topic_id": "topic_001", "title": "Plan", "summary": "Do X", "citations": [{"segment_id": 0}]}],
            "decisions": [{"decision_id": "dec_001", "text": "Do X", "citations": [{"segment_id": 0}]}],
            "action_items": [{"action_id": "act_001", "text": "Implement X", "assignee": "SPEAKER_00", "due_date": None, "citations": [{"segment_id": 0}]}],
            "notes": [{"note_id": "note_0000", "text": "We should do X.", "citations": [{"segment_id": 0}]}],
            "open_questions": [],
        }
        return json.dumps(payload)

    monkeypatch.setattr(mod, "_call_openai_minutes_json", fake_call_openai_minutes_json)

    art = formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")
    assert art["kind"] == "minutes_json"

    payload = json.loads((run_dir / "artifacts" / "minutes.json").read_text(encoding="utf-8"))
    assert payload["decisions"][0]["citations"][0]["segment_id"] == 0
    assert payload["action_items"][0]["citations"][0]["segment_id"] == 0


def test_formalize_minutes_hybrid_invalid_json_fails_loud(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run_003"
    _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "HYBRID")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    from ashby.modules.meetings.formalize import minutes_json as mod

    monkeypatch.setattr(mod, "_call_openai_minutes_json", lambda **kwargs: "NOT JSON")

    with pytest.raises(ValueError):
        formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")

    assert (run_dir / "artifacts" / "minutes_llm_raw.txt").exists()
    assert (run_dir / "artifacts" / "minutes_llm_failure.json").exists()
