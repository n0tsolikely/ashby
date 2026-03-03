from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from tests.chat_test_utils import seed_chat_index


@pytest.mark.asyncio
async def test_session_scope_no_leak_from_other_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    monkeypatch.setenv("STUART_LLM_GATEWAY_URL", "http://127.0.0.1:1")
    seed_chat_index(root)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/api/chat", json={"session_id": "ses_a", "text": "budget", "ui": {"selected_session_id": "ses_a"}})
    assert r.status_code == 200
    body = r.json()
    reply = body.get("reply") or {}
    for cit in reply.get("citations") or []:
        assert cit.get("session_id") == "ses_a"
