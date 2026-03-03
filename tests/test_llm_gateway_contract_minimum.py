from __future__ import annotations

import json

import pytest

from ashby.interfaces.llm_gateway.providers.gemini import GeminiProvider
from ashby.interfaces.llm_gateway.schemas import FormalizeRequest


def _request(*, mode: str, retention: str) -> FormalizeRequest:
    return FormalizeRequest(
        transcript_text="Speaker A: hello",
        mode=mode,  # type: ignore[arg-type]
        template_id="default",
        retention=retention,  # type: ignore[arg-type]
        profile="HYBRID",
    )


def test_prompt_is_retention_aware(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiProvider()

    low_prompt = provider._build_prompt(_request(mode="meeting", retention="LOW"))
    high_prompt = provider._build_prompt(_request(mode="meeting", retention="HIGH"))

    assert "Retention policy:" in low_prompt
    assert "Retention policy:" in high_prompt
    assert low_prompt != high_prompt


def test_mapping_keeps_at_least_one_content_item_for_non_low_retentions() -> None:
    req_meeting = _request(mode="meeting", retention="HIGH")
    out_meeting = GeminiProvider._map_text_to_output_json(req_meeting, text="")
    assert isinstance(out_meeting.get("notes"), list)
    assert len(out_meeting["notes"]) >= 1
    assert out_meeting["notes"][0]["citations"][0]["segment_id"] == 0

    req_journal = _request(mode="journal", retention="NEAR_VERBATIM")
    out_journal = GeminiProvider._map_text_to_output_json(req_journal, text="")
    assert isinstance(out_journal.get("narrative_sections"), list)
    assert len(out_journal["narrative_sections"]) >= 1


def test_structured_provider_output_falls_back_when_output_json_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiProvider()

    # Provider text that is JSON but does not include output_json should still map safely.
    fake_json = json.dumps({"summary": "hello"})
    out = provider._map_text_to_output_json(_request(mode="meeting", retention="MED"), text=fake_json)
    assert isinstance(out, dict)
    assert "notes" in out

