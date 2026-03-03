from __future__ import annotations

import json
from typing import Any, Dict

import httpx

from ashby.modules.llm.http_gateway import HTTPGatewayLLMService
from ashby.modules.llm.service import LLMChatEvidenceSegment, LLMChatRequest


def test_llm_chat_client_posts_expected_payload() -> None:
    seen: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "version": 1,
                "request_id": "req_chat_1",
                "output_json": {"text": "ok", "citations": [], "actions": []},
                "usage": {"total_tokens": 10},
                "timing_ms": 8,
                "provider": "gemini",
                "model": "gemini-test",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    svc = HTTPGatewayLLMService(base_url="http://gateway.local", client=client)
    req = LLMChatRequest(
        question="what did we decide",
        scope="session",
        ui_state={"selected_session_id": "ses_1"},
        history_tail=[{"role": "user", "text": "earlier"}],
        evidence_segments=[
            LLMChatEvidenceSegment(
                session_id="ses_1",
                run_id="run_1",
                segment_id=1,
                text="decided to ship",
                speaker_label="SPEAKER_00",
            )
        ],
    )
    out = svc.chat(req)

    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/chat"
    assert seen["json"]["question"] == "what did we decide"
    assert seen["json"]["evidence_segments"][0]["segment_id"] == 1
    assert out.request_id == "req_chat_1"
    assert out.output_json["text"] == "ok"
