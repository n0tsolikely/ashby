from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from tests.chat_test_utils import seed_chat_index


@pytest.mark.asyncio
async def test_integration_global_cold_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    monkeypatch.setenv("STUART_LLM_GATEWAY_URL", "http://127.0.0.1:1")
    seed_chat_index(root)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/api/chat/global", json={"text": "roadmap", "ui": {}, "history_tail": []})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("scope") == "global"
