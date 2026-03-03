from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from tests.chat_test_utils import seed_chat_index


@pytest.mark.asyncio
async def test_chat_global_focus_can_open_other_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))
    seed_chat_index(root)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post(
            "/api/chat/global",
            json={
                "text": "budget",
                "ui": {"selected_session_id": "ses_a"},
                "history_tail": [],
            },
        )

    assert r.status_code == 200
    body = r.json()
    actions = ((body.get("reply") or {}).get("actions") or [])
    open_actions = [a for a in actions if a.get("kind") == "open_session"]
    assert any(a.get("session_id") == "ses_b" for a in open_actions)
