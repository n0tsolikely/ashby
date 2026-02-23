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


def _formalize_params_from_state(state: dict) -> dict:
    plan = (state or {}).get("plan") or {}
    steps = plan.get("steps") or []
    for st in steps:
        if not isinstance(st, dict):
            continue
        if str(st.get("kind") or "").strip().lower() == "formalize":
            return st.get("params") or {}
    return {}


@pytest.mark.asyncio
async def test_web_reformalize_endpoint_reuses_transcripts(tmp_path: Path, monkeypatch):
    """QUEST_071: user can reformalize (template/retention) without re-ingesting audio."""

    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.post("/api/sessions", json={"mode": "journal", "title": "web test"})
        sid = r.json()["session_id"]

        wav_bytes = _gen_wav_bytes(tmp_path)
        r2 = await c.post(
            f"/api/upload?session_id={sid}",
            content=wav_bytes,
            headers={"x-filename": "test.wav", "content-type": "audio/wav"},
        )
        assert r2.json().get("ok") is True

        # Start the base run (first formalize)
        r3 = await c.post(
            "/api/run",
            json={"session_id": sid, "ui": {"mode": "journal", "template": "default", "speakers": None}},
        )
        j3 = r3.json()
        assert j3.get("ok") is True
        base_run_id = j3["run_id"]

        # Poll base run to completion.
        for _ in range(60):
            st = (await c.get(f"/api/runs/{base_run_id}")).json()
            status = (st.get("state") or {}).get("status")
            if status in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.05)

        st = (await c.get(f"/api/runs/{base_run_id}")).json()
        assert (st.get("state") or {}).get("status") == "succeeded"

        # Re-formalize with a different retention.
        r4 = await c.post(
            f"/api/runs/{base_run_id}/reformalize",
            json={"template_id": "default", "retention": "HIGH"},
        )
        j4 = r4.json()
        assert j4.get("ok") is True
        rerun_run_id = j4["rerun_run_id"]

        # Poll rerun to completion.
        for _ in range(80):
            st2 = (await c.get(f"/api/runs/{rerun_run_id}")).json()
            status2 = (st2.get("state") or {}).get("status")
            if status2 in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.05)

        st2 = (await c.get(f"/api/runs/{rerun_run_id}")).json()
        state2 = st2.get("state") or {}
        assert state2.get("status") == "succeeded"

        # Plan must record changed retention + reuse linkage.
        fp = _formalize_params_from_state(state2)
        assert fp.get("retention") == "HIGH"
        assert fp.get("template_id") == "default"
        assert fp.get("reuse_run_id") == base_run_id

        # Run artifacts should show reuse rails (skip normalize + reused transcript receipt).
        kinds = {a.get("kind") for a in (state2.get("artifacts") or []) if isinstance(a, dict)}
        assert "normalize_skipped" in kinds
        assert "reused_transcript_receipt" in kinds
    finally:
        await c.aclose()
