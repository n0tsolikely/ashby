from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app


def _gen_wav_bytes(tmp_path: Path) -> bytes:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not installed")
    p = tmp_path / "upload.wav"
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(p)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return p.read_bytes()


@pytest.mark.asyncio
async def test_web_upload_and_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await asyncio.wait_for(c.post("/api/sessions", json={"mode": "journal", "title": "web test"}), timeout=10)
        sid = r.json()["session_id"]

        wav_bytes = _gen_wav_bytes(tmp_path)
        r2 = await asyncio.wait_for(
            c.post(
                f"/api/upload?session_id={sid}",
                content=wav_bytes,
                headers={"x-filename": "test.wav", "content-type": "audio/wav"},
            ),
            timeout=10,
        )
        j = r2.json()
        assert j["ok"] is True
        att = j["attachment"]

        r3 = await asyncio.wait_for(
            c.post(
                "/api/message",
                json={
                    "session_id": sid,
                    "text": "formalize this",
                    "ui": {"mode": "journal", "template": None, "speakers": None},
                    "attachments": [att],
                },
            ),
            timeout=10,
        )
        out = r3.json()["result"]
        assert out["needs_clarification"] is False

        r4 = await asyncio.wait_for(
            c.post(
                "/api/run",
                json={"session_id": sid, "ui": {"mode": "journal", "template": "default", "speakers": None}},
            ),
            timeout=10,
        )
        j4 = r4.json()
        assert j4["ok"] is True
        run_id = j4["run_id"]

        # poll status
        for _ in range(50):
            st = (await asyncio.wait_for(c.get(f"/api/runs/{run_id}"), timeout=10)).json()
            status = (st.get("state") or {}).get("status")
            if status in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.05)

        st = (await asyncio.wait_for(c.get(f"/api/runs/{run_id}"), timeout=10)).json()
        assert (st.get("state") or {}).get("status") == "succeeded"
        arts = st.get("artifacts") or []
        assert len(arts) >= 1

        # QUEST_063: deterministic primary downloads derived from run.json["primary_outputs"]
        downloads = st.get("downloads") or {}
        primary = downloads.get("primary") or {}
        pdf = primary.get("pdf")
        txt = primary.get("txt")
        assert isinstance(pdf, dict)
        assert isinstance(txt, dict)
        url = pdf.get("url")
        assert isinstance(url, str)
        assert url.startswith(f"/download/{run_id}/")
        txt_url = txt.get("url")
        assert isinstance(txt_url, str)
        assert txt_url.startswith(f"/download/{run_id}/")

        # ensure filename was not guessed (it must match the pointer path basename)
        po = (st.get("state") or {}).get("primary_outputs") or {}
        ppdf = po.get("pdf") or {}
        assert Path(ppdf.get("path") or "").name == pdf.get("name")

        resp = await asyncio.wait_for(c.get(url), timeout=10)
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF")
    finally:
        await c.aclose()
