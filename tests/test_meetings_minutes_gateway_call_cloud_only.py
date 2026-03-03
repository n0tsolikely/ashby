from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.llm.service import LLMFormalizeResponse
from ashby.modules.meetings.formalize.minutes_json import formalize_meeting_to_minutes_json


def _write_aligned_transcript(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "ses_cloud",
        "run_id": run_dir.name,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "Cloud route test."},
        ],
        "engine": "test",
    }
    (artifacts / "aligned_transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_gateway_called_when_profile_cloud_and_remote_enabled(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_cloud"
    _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "CLOUD")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    from ashby.modules.meetings.formalize import minutes_json as mod

    called = {"count": 0}

    class _FakeGateway:
        def formalize(self, request, *, artifacts_dir=None):
            called["count"] += 1
            assert request.profile == "CLOUD"
            assert request.transcript_text
            assert request.transcript_segments is not None
            assert len(request.transcript_segments) == 1
            assert request.transcript_segments[0].segment_id == "0"
            assert request.template_text
            assert request.template_sections is not None
            assert len(request.template_sections) >= 1
            assert request.include_citations is False
            assert request.show_empty_sections is False
            payload = {
                "version": 1,
                "session_id": "ses_cloud",
                "run_id": "run_cloud",
                "header": {"title": "T", "mode": "meeting", "retention": "MED", "template_id": "default"},
                "participants": [],
                "topics": [],
                "decisions": [],
                "action_items": [],
                "notes": [{"note_id": "note_0001", "text": "Cloud route test.", "citations": [{"segment_id": 0}]}],
                "open_questions": [],
            }
            return LLMFormalizeResponse(
                version=1,
                request_id="req_cloud",
                output_json=payload,
                evidence_map={},
                usage={"char_count": 16},
                timing_ms=1,
                provider="gemini",
                model="gemini-test",
            )

    monkeypatch.setattr(mod, "HTTPGatewayLLMService", _FakeGateway)

    art = formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")
    assert art["kind"] == "minutes_json"
    assert called["count"] == 1
    out = json.loads((run_dir / "artifacts" / "minutes.json").read_text(encoding="utf-8"))
    assert out["template_id"] == "default"
    assert out["template_version"] == "2"
    assert out["retention"] == "MED"
    assert out["include_citations"] is False
    assert out["show_empty_sections"] is False
