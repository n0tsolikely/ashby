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
        return self._payload


def _valid_meeting_output() -> Dict[str, Any]:
    return {
        "header": {"title": "Meeting Minutes"},
        "participants": [],
        "topics": [],
        "decisions": [],
        "action_items": [],
        "notes": [],
        "open_questions": [],
    }


@pytest.mark.asyncio
async def test_health_and_formalize_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    app = create_app()
    app.state.provider = _FakeProvider(
        {
            "output_json": _valid_meeting_output(),
            "evidence_map": {"units": []},
            "usage": {"char_count": 11},
        }
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        h = await client.get("/health")
        assert h.status_code == 200
        assert h.json()["ok"] is True
        assert h.json()["version"] == 1

        r = await client.post(
            "/v1/formalize",
            json={
                "transcript_text": "hello world",
                "mode": "meeting",
                "template_id": "default",
                "retention": "MED",
                "profile": "HYBRID",
            },
        )
    body = r.json()
    assert r.status_code == 200
    assert body["version"] == 1
    assert body["request_id"]
    assert body["output_json"]["version"] == 1
    assert body["provider"] == "gemini"


@pytest.mark.asyncio
async def test_startup_fails_without_gemini_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = create_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
    body = r.json()
    assert r.status_code == 503
    assert body["ok"] is False
    assert body["version"] == 1
    assert "GEMINI_API_KEY is required" in body["error"]["message"]


@pytest.mark.asyncio
async def test_request_validation_422_includes_version_and_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    app = create_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/formalize",
            json={
                "mode": "meeting",
                "template_id": "default",
                "retention": "MED",
            },
        )
    body = r.json()
    assert r.status_code == 422
    assert body["ok"] is False
    assert body["version"] == 1
    assert isinstance(body["request_id"], str) and body["request_id"]


@pytest.mark.asyncio
async def test_schema_validation_422_includes_version_and_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    app = create_app()
    app.state.provider = _FakeProvider({"output_json": []})
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/formalize",
            json={
                "transcript_text": "hello",
                "mode": "meeting",
                "template_id": "default",
                "retention": "MED",
                "profile": "HYBRID",
            },
        )
    body = r.json()
    assert r.status_code == 422
    assert body["ok"] is False
    assert body["version"] == 1
    assert isinstance(body["request_id"], str) and body["request_id"]
