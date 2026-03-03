from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from ashby.modules.meetings.store import create_session


@pytest.mark.asyncio
async def test_export_api_accepts_dev_bundle_and_returns_traceable_filename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    sid = create_session(mode="meeting", title="My Session Title")
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await asyncio.wait_for(
            c.get(f"/api/sessions/{sid}/export?export_type=dev_bundle"),
            timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        z = body.get("zip") or {}
        dn = str(z.get("download_name") or "")
        assert sid in dn
        assert "export_dev_bundle" in dn
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_export_api_validates_format_params(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    sid = create_session(mode="meeting", title="Export Validation")
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        bad_t = await asyncio.wait_for(
            c.get(f"/api/sessions/{sid}/export?export_type=full_bundle&transcript_formats=txt,exe"),
            timeout=10,
        )
        assert bad_t.status_code == 400
        assert (bad_t.json().get("error") or {}).get("code") == "INVALID_REQUEST"

        bad_f = await asyncio.wait_for(
            c.get(f"/api/sessions/{sid}/export?export_type=full_bundle&formalization_formats=pdf,json"),
            timeout=10,
        )
        assert bad_f.status_code == 400
        assert (bad_f.json().get("error") or {}).get("code") == "INVALID_REQUEST"

        ok_default = await asyncio.wait_for(
            c.get(f"/api/sessions/{sid}/export?export_type=full_bundle"),
            timeout=10,
        )
        payload = ok_default.json()
        assert ok_default.status_code == 200
        assert payload.get("ok") is True
        assert payload.get("transcript_formats") == ["txt"]
        assert payload.get("formalization_formats") == ["pdf"]
    finally:
        await c.aclose()
