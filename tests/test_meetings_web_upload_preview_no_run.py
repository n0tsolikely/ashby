from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app


@pytest.mark.asyncio
async def test_web_upload_returns_plan_preview_and_does_not_start_run(tmp_path: Path, monkeypatch):
    """QUEST_062 rail: upload stores contribution only (no processing), returns plan preview."""

    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        # Create an explicit session (journal) and upload bytes.
        r = await c.post("/api/sessions", json={"mode": "journal", "title": "web test"})
        sid = r.json()["session_id"]

        r2 = await c.post(
            f"/api/upload?session_id={sid}",
            content=b"fake-wav-bytes",
            headers={"x-filename": "test.wav", "content-type": "audio/wav"},
        )
        j = r2.json()
        assert j["ok"] is True
        assert j["session_id"] == sid
        assert isinstance(j.get("contribution_id"), str) and j["contribution_id"]

        rs = await c.get("/api/sessions")
        sj = rs.json()
        assert sj["ok"] is True
        row = next((x for x in sj.get("sessions", []) if x.get("session_id") == sid), None)
        assert isinstance(row, dict)
        assert int(row.get("contributions_count") or 0) >= 1
        assert row.get("has_audio") is True

        # Plan preview must be present and must disclose defaults.
        pp = j.get("plan_preview")
        assert isinstance(pp, dict)
        assert pp.get("mode") == "journal"
        assert pp.get("template") == "default"
        assert pp.get("speakers") == "1"  # journal default
        defaults_used = pp.get("defaults_used") or []
        assert "retention=MED" in defaults_used
        assert "template=default" in defaults_used

        kinds = [s.get("kind") for s in (pp.get("ordered_steps") or []) if isinstance(s, dict)]
        assert "validate" in kinds
        assert "formalize" in kinds

        # No run should exist yet.
        runs_dir = tmp_path / "stuart_runtime" / "runs"
        assert runs_dir.exists()
        assert list(runs_dir.iterdir()) == []

        # Also support implicit session creation when session_id is omitted.
        r3 = await c.post(
            "/api/upload?mode=meeting",
            content=b"fake-wav-bytes-2",
            headers={"x-filename": "test2.wav", "content-type": "audio/wav"},
        )
        j3 = r3.json()
        assert j3["ok"] is True
        assert isinstance(j3.get("session_id"), str) and j3["session_id"]
        assert isinstance(j3.get("contribution_id"), str) and j3["contribution_id"]
        pp3 = j3.get("plan_preview")
        assert isinstance(pp3, dict)
        assert pp3.get("mode") == "meeting"
        assert pp3.get("template") == "default"
        assert pp3.get("speakers") == "auto"  # meeting default

        # Still no runs created by upload.
        assert list(runs_dir.iterdir()) == []
