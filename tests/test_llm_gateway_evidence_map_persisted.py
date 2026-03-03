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
        "session_id": "ses_evm",
        "run_id": run_dir.name,
        "segments": [{"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "Evidence map test."}],
        "engine": "test",
    }
    (artifacts / "aligned_transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_gateway_evidence_map_is_persisted_and_validated(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_evm"
    _write_aligned_transcript(run_dir)

    monkeypatch.setenv("ASHBY_EXECUTION_PROFILE", "HYBRID")
    monkeypatch.setenv("ASHBY_MEETINGS_LLM_ENABLED", "1")

    from ashby.modules.meetings.formalize import minutes_json as mod

    class _FakeGateway:
        def formalize(self, _request, *, artifacts_dir=None):
            payload = {
                "version": 1,
                "session_id": "ses_evm",
                "run_id": "run_evm",
                "header": {"title": "T", "mode": "meeting", "retention": "MED", "template_id": "default"},
                "participants": [],
                "topics": [],
                "decisions": [],
                "action_items": [],
                "notes": [{"note_id": "note_0001", "text": "Evidence map test.", "citations": [{"segment_id": 0}]}],
                "open_questions": [],
            }
            evm = {
                "version": 2,
                "session_id": "ses_evm",
                "run_id": "run_evm",
                "mode": "meeting",
                "claims": [
                    {
                        "claim_id": "claim_001",
                        "claim_type": "minutes.note",
                        "claim_text": "Evidence map test.",
                        "anchors": [
                            {
                                "segment_id": 0,
                                "t_start": 0.0,
                                "t_end": 1.0,
                                "speaker_label": "SPEAKER_00",
                            }
                        ],
                    }
                ],
            }
            return LLMFormalizeResponse(
                version=1,
                request_id="req_evm",
                output_json=payload,
                evidence_map=evm,
                usage={"char_count": 17},
                timing_ms=2,
                provider="gemini",
                model="gemini-test",
            )

    monkeypatch.setattr(mod, "HTTPGatewayLLMService", _FakeGateway)
    formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")

    evm_path = run_dir / "artifacts" / "evidence_map_llm.json"
    assert evm_path.exists()
    evm_payload = json.loads(evm_path.read_text(encoding="utf-8"))
    assert evm_payload["version"] == 2
    assert evm_payload["claims"][0]["anchors"][0]["segment_id"] == 0

