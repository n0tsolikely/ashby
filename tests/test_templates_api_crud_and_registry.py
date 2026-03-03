from __future__ import annotations

import httpx
import pytest

from ashby.interfaces.web.app import create_app


@pytest.mark.asyncio
async def test_templates_api_crud_and_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        created = await c.post(
            "/api/templates",
            json={
                "mode": "meeting",
                "template_title": "API Template",
                "template_text": "## Intro\n\n## Decisions\n",
                "defaults": {"include_citations": True, "show_empty_sections": False},
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["ok"] is True
        tid = body["template"]["descriptor"]["template_id"]
        assert body["template"]["descriptor"]["template_version"] == "1"

        draft = await c.post(
            "/api/templates/draft",
            json={
                "mode": "meeting",
                "source_kind": "text",
                "raw_text": "Agenda\nDecisions\nActions",
                "template_title": "Imported Draft",
            },
        )
        assert draft.status_code == 200
        draft_payload = draft.json()
        assert draft_payload["ok"] is True
        assert "##" in draft_payload["draft"]["template_text"]

        listed = await c.get("/api/templates", params={"mode": "meeting"})
        assert listed.status_code == 200
        rows = listed.json()["items"]
        assert any(r["template_id"] == tid for r in rows)

        versions = await c.get(f"/api/templates/{tid}/versions", params={"mode": "meeting"})
        assert versions.status_code == 200
        assert versions.json()["versions"] == [1]

        created_v2 = await c.post(
            "/api/templates",
            json={
                "mode": "meeting",
                "template_id": tid,
                "template_title": "API Template v2",
                "template_text": "## Intro\n\n## Decisions\n\n## Risks\n",
            },
        )
        assert created_v2.status_code == 200
        assert created_v2.json()["template"]["descriptor"]["template_version"] == "2"

        registry = await c.get("/api/registry")
        assert registry.status_code == 200
        payload = registry.json()
        assert any(r["template_id"] == tid and r["template_title"] == "API Template v2" for r in payload["templates_by_mode"]["meeting"])

        missing_confirm = await c.delete(f"/api/templates/{tid}", params={"mode": "meeting"})
        assert missing_confirm.status_code == 400

        deleted = await c.delete(f"/api/templates/{tid}", params={"mode": "meeting", "confirm": "true"})
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
