from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.llm.service import LLMFormalizeResponse
from ashby.modules.meetings.formalize.minutes_json import formalize_meeting_to_minutes_json
from ashby.modules.meetings.schemas.minutes_v1 import validate_minutes_v1


def _write_aligned_transcript(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "ses_sanitize",
        "run_id": run_dir.name,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "We agreed on the next step."},
        ],
        "engine": "test",
    }
    (artifacts / "aligned_transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_minutes_json_string_field_is_sanitized_before_write(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_sanitize"
    _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "CLOUD")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    from ashby.modules.meetings.formalize import minutes_json as mod

    class _FakeGateway:
        def formalize(self, request, *, artifacts_dir=None):
            payload = {
                "version": 1,
                "session_id": "ses_sanitize",
                "run_id": "run_sanitize",
                "header": {"title": "T", "mode": "meeting", "retention": "MED", "template_id": "default"},
                "participants": [],
                "topics": [],
                "decisions": [],
                "action_items": [],
                "notes": [
                    {
                        "note_id": "note_0001",
                        "text": "{\"header\":{\"title\":\"X\"},\"notes\":[{\"text\":\"Action agreed for Friday.\"}]}",
                        "citations": [{"segment_id": 0}],
                    }
                ],
                "open_questions": [],
            }
            return LLMFormalizeResponse(
                version=1,
                request_id="req_sanitize",
                output_json=payload,
                evidence_map={},
                usage={"char_count": 20},
                timing_ms=1,
                provider="gemini",
                model="gemini-test",
            )

    monkeypatch.setattr(mod, "HTTPGatewayLLMService", _FakeGateway)

    art = formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")
    assert art["kind"] == "minutes_json"

    payload = json.loads((run_dir / "artifacts" / "minutes.json").read_text(encoding="utf-8"))
    validate_minutes_v1(payload)

    note_text = payload["notes"][0]["text"]
    assert isinstance(note_text, str) and note_text.strip()
    assert "Action agreed for Friday." in note_text
    assert "{" not in note_text
    assert "}" not in note_text
    assert '\\"' not in note_text
