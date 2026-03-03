from __future__ import annotations

from typing import Any, Dict

import httpx
import pytest

from ashby.interfaces.llm_gateway.app import create_app


class _FakeProvider:
    provider_name = "gemini"
    model = "gemini-test"

    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def formalize(self, _req: Any) -> Dict[str, Any]:
        return {"output_json": {"header": {"title": "x"}, "participants": [], "topics": [], "decisions": [], "action_items": [], "notes": [], "open_questions": []}}

    def chat(self, _req: Any) -> Dict[str, Any]:
        return self._payload


@pytest.mark.asyncio
async def test_chat_gateway_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    app = create_app()
    app.state.provider = _FakeProvider(
        {
            "output_json": {
                "text": "Answer based on evidence.",
                "citations": [{"session_id": "ses_1", "run_id": "run_1", "segment_id": 1}],
                "actions": [{"kind": "open_session", "session_id": "ses_1"}],
            },
            "usage": {"char_count": 22},
        }
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/chat",
            json={
                "question": "what was decided?",
                "scope": "session",
                "ui_state": {},
                "history_tail": [],
                "evidence_segments": [{"session_id": "ses_1", "run_id": "run_1", "segment_id": 1, "text": "decision text"}],
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert body["output_json"]["text"]
    assert body["output_json"]["citations"][0]["session_id"] == "ses_1"


@pytest.mark.asyncio
async def test_chat_gateway_invalid_output_422(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    app = create_app()
    app.state.provider = _FakeProvider({"output_json": {"text": "", "citations": [], "actions": []}})
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/chat",
            json={
                "question": "q",
                "scope": "session",
                "ui_state": {},
                "history_tail": [],
                "evidence_segments": [{"session_id": "ses_1", "run_id": "run_1", "segment_id": 1, "text": "x"}],
            },
        )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"
