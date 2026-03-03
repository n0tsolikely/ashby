from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.llm.service import LLMFormalizeResponse
from ashby.modules.meetings.formalize.journal_json import formalize_journal_to_journal_json


def _write_aligned_transcript(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "ses_cloud_journal",
        "run_id": run_dir.name,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "Journal cloud test."},
        ],
        "engine": "test",
    }
    (artifacts / "aligned_transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_gateway_called_when_profile_cloud_and_remote_enabled(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_cloud_journal"
    _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "CLOUD")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    from ashby.modules.meetings.formalize import journal_json as mod

    called = {"count": 0}

    class _FakeGateway:
        def formalize(self, request, *, artifacts_dir=None):
            called["count"] += 1
            assert request.profile == "CLOUD"
            payload = {
                "version": 1,
                "session_id": "ses_cloud_journal",
                "run_id": "run_cloud_journal",
                "header": {"title": "T", "mode": "journal", "retention": "MED", "template_id": "default"},
                "narrative_sections": [{"section_id": "sec_001", "text": "Journal cloud test."}],
                "key_points": [],
                "action_items": [],
                "feelings": [],
                "mood": "",
            }
            return LLMFormalizeResponse(
                version=1,
                request_id="req_cloud",
                output_json=payload,
                evidence_map={},
                usage={"char_count": 18},
                timing_ms=1,
                provider="gemini",
                model="gemini-test",
            )

    monkeypatch.setattr(mod, "HTTPGatewayLLMService", _FakeGateway)

    art = formalize_journal_to_journal_json(run_dir, template_id="default", retention="MED")
    assert art["kind"] == "journal_json"
    assert called["count"] == 1

