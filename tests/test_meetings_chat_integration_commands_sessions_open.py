from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from tests.chat_test_utils import seed_chat_index


@pytest.mark.asyncio
async def test_integration_commands_sessions_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    seed_chat_index(root)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/api/chat/global", json={"text": "/sessions", "ui": {}})

    assert r.status_code == 200
    reply = (r.json().get("reply") or {})
    actions = reply.get("actions") or []
    assert any(a.get("kind") == "open_session" for a in actions)
