from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.llm.service import LLMFormalizeResponse
from ashby.modules.meetings.formalize.minutes_json import formalize_meeting_to_minutes_json


def _write_aligned_transcript(run_dir: Path) -> str:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    transcript_text = "Sensitive transcript text should not be in llm_usage receipt."
    payload = {
        "version": 1,
        "session_id": "ses_usage",
        "run_id": run_dir.name,
        "segments": [{"segment_id": 0, "speaker": "SPEAKER_00", "text": transcript_text}],
        "engine": "test",
    }
    (artifacts / "aligned_transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return transcript_text


def test_llm_usage_receipt_no_transcript_or_prompt_leak(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_usage"
    secret_text = _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "HYBRID")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    from ashby.modules.meetings.formalize import minutes_json as mod

    class _FakeGateway:
        def formalize(self, _request, *, artifacts_dir=None):
            payload = {
                "version": 1,
                "session_id": "ses_usage",
                "run_id": "run_usage",
                "header": {"title": "T", "mode": "meeting", "retention": "MED", "template_id": "default"},
                "participants": [],
                "topics": [],
                "decisions": [],
                "action_items": [],
                "notes": [{"note_id": "note_0001", "text": "ok", "citations": [{"segment_id": 0}]}],
                "open_questions": [],
            }
            return LLMFormalizeResponse(
                version=1,
                request_id="req_usage",
                output_json=payload,
                evidence_map={},
                usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3, "char_count": 42},
                timing_ms=5,
                provider="gemini",
                model="gemini-test",
            )

    monkeypatch.setattr(mod, "HTTPGatewayLLMService", _FakeGateway)
    formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")

    usage_path = run_dir / "artifacts" / "llm_usage.json"
    assert usage_path.exists()
    usage_raw = usage_path.read_text(encoding="utf-8")
    usage = json.loads(usage_raw)

    assert usage["version"] == 1
    assert usage["provider"] == "gemini"
    assert usage["request_id"] == "req_usage"
    assert usage["policy_sha256"]
    assert "transcript_text" not in usage
    assert "prompt_text" not in usage
    assert "prompt_text" not in usage_raw
    assert "full_prompt" not in usage_raw
    assert secret_text not in usage_raw
