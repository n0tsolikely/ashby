from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from tests.chat_test_utils import seed_chat_index


@pytest.mark.asyncio
async def test_integration_citations_actions_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    monkeypatch.setenv("STUART_LLM_GATEWAY_URL", "http://127.0.0.1:1")
    seed_chat_index(root)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/api/chat/global", json={"text": "roadmap", "ui": {"selected_session_id": "ses_b"}})

    assert r.status_code == 200
    reply = (r.json().get("reply") or {})
    assert isinstance(reply.get("citations"), list)
    assert isinstance(reply.get("actions"), list)
    for action in reply.get("actions") or []:
        assert action.get("kind") in {"open_session", "jump_to_segment"}
