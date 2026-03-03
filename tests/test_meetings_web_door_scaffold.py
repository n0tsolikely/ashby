from __future__ import annotations

import httpx
import pytest

from ashby.interfaces.web.app import create_app


@pytest.mark.asyncio
async def test_web_registry_exposes_modes_and_templates():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/api/registry")
    assert r.status_code == 200
    data = r.json()
    assert "modes" in data
    assert "templates_by_mode" in data
    assert "journal" in data["modes"]
    assert "meeting" in data["modes"]
    journal = data["templates_by_mode"]["journal"]
    meeting = data["templates_by_mode"]["meeting"]
    assert isinstance(journal, list) and isinstance(meeting, list)
    assert any(row.get("template_id") == "default" for row in journal)
    assert any(row.get("template_id") == "default" for row in meeting)


@pytest.mark.asyncio
async def test_index_has_mode_placeholder_and_no_default_selected():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/")
    assert r.status_code == 200
    html = r.text
    # placeholder must exist and be disabled so nothing is preselected
    assert '<option value="" selected disabled>Mode</option>' in html


@pytest.mark.asyncio
async def test_index_has_library_and_search_controls():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/")
    assert r.status_code == 200
    html = r.text
    # QUEST_064: basic library/search UI controls exist
    assert 'id="searchInput"' in html
    assert 'id="searchBtn"' in html
    assert 'id="libraryBtn"' in html


@pytest.mark.asyncio
async def test_web_library_endpoint_returns_ok_even_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/api/library?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "sessions" in data
