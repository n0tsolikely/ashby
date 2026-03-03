from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from ashby.interfaces.web.app import create_app
from ashby.modules.meetings.store import add_contribution, create_run, create_session, get_run_state, update_run_state


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
async def test_api_run_persists_title_and_patch_renames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    sid = create_session(mode="meeting", title="Title Test")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(_gen_wav_bytes(tmp_path))
    add_contribution(session_id=sid, source_path=audio, source_kind="audio")

    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await asyncio.wait_for(
            c.post(
                "/api/run",
                json={
                    "session_id": sid,
                    "ui": {"mode": "meeting", "template": "default", "formalization_title": "  My   Draft  "},
                },
            ),
            timeout=10,
        )
        body = r.json()
        assert r.status_code == 200
        assert body.get("ok") is True
        run_id = str(body.get("run_id") or "")
        assert run_id

        st = get_run_state(run_id)
        assert st.get("title_override") == "My Draft"

        rp = await asyncio.wait_for(
            c.patch(f"/api/runs/{run_id}", json={"formalization_title": "Renamed Title"}),
            timeout=10,
        )
        bp = rp.json()
        assert rp.status_code == 200
        assert bp.get("ok") is True
        assert (bp.get("formalization_title") or "") == "Renamed Title"

        st2 = get_run_state(run_id)
        assert st2.get("title_override") == "Renamed Title"

        # Drain background run thread before test teardown to avoid cross-test warnings.
        for _ in range(100):
            st_api = await asyncio.wait_for(c.get(f"/api/runs/{run_id}"), timeout=10)
            status = ((st_api.json().get("state") or {}).get("status") or "").strip().lower()
            if status in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.05)
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_formalizations_list_includes_title_override_or_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    sid = create_session(mode="meeting", title="Session One")
    run1 = create_run(
        session_id=sid,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template_id": "default"}}]},
        title_override="Alpha",
    )
    art1 = tmp_path / "stuart_runtime" / "runs" / run1 / "artifacts"
    art1.mkdir(parents=True, exist_ok=True)
    (art1 / "minutes.md").write_text("# Minutes\n", encoding="utf-8")
    update_run_state(
        run1,
        status="succeeded",
        primary_outputs={"md": {"path": "artifacts/minutes.md", "kind": "minutes_md"}},
    )

    run2 = create_run(
        session_id=sid,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "journal", "template_id": "default"}}]},
    )
    art2 = tmp_path / "stuart_runtime" / "runs" / run2 / "artifacts"
    art2.mkdir(parents=True, exist_ok=True)
    (art2 / "journal.md").write_text("# Journal\n", encoding="utf-8")
    update_run_state(
        run2,
        status="succeeded",
        primary_outputs={"md": {"path": "artifacts/journal.md", "kind": "journal_md"}},
    )

    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await asyncio.wait_for(c.get(f"/api/sessions/{sid}/formalizations"), timeout=10)
        body = r.json()
        assert r.status_code == 200
        assert body.get("ok") is True
        rows = body.get("formalizations") or []
        by_id = {str(x.get("run_id")): x for x in rows if isinstance(x, dict)}

        assert by_id[run1].get("title") == "Alpha"
        assert isinstance(by_id[run2].get("title"), str)
        assert by_id[run2]["title"].startswith("Session One - journal - ")
    finally:
        await c.aclose()
