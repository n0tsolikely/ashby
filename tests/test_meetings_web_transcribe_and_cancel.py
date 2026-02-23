from __future__ import annotations

import asyncio
import json
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
        [ff, "-y", "-f", "lavfi", "-i", "sine=frequency=900:duration=0.6", str(p)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return p.read_bytes()


@pytest.mark.asyncio
async def test_transcribe_endpoint_and_no_audio_guard(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.post("/api/sessions", json={"mode": "meeting", "title": "guard"})
        sid = r.json()["session_id"]

        no_audio_run = await c.post("/api/run", json={"session_id": sid, "ui": {"mode": "meeting"}})
        assert no_audio_run.status_code == 400
        assert (no_audio_run.json().get("error") or {}).get("code") == "NO_AUDIO"

        no_audio_transcribe = await c.post("/api/transcribe", json={"session_id": sid, "mode": "meeting"})
        assert no_audio_transcribe.status_code == 400
        assert (no_audio_transcribe.json().get("error") or {}).get("code") == "NO_AUDIO"

        wav_bytes = _gen_wav_bytes(tmp_path)
        up = await c.post(
            f"/api/upload?session_id={sid}",
            content=wav_bytes,
            headers={"x-filename": "test.wav", "content-type": "audio/wav"},
        )
        assert up.status_code == 200

        tr = await c.post(
            "/api/transcribe",
            json={"session_id": sid, "mode": "meeting", "diarization_enabled": False},
        )
        assert tr.status_code == 200
        run_id_off = tr.json()["run_id"]

        for _ in range(80):
            st = (await c.get(f"/api/runs/{run_id_off}")).json()
            status = ((st.get("state") or {}).get("status") or "").lower()
            if status in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.05)

        st = (await c.get(f"/api/runs/{run_id_off}")).json()
        status = ((st.get("state") or {}).get("status") or "").lower()
        assert status == "succeeded"
        po = ((st.get("state") or {}).get("primary_outputs") or {})
        assert isinstance(po.get("transcript"), dict)
        downloads = (st.get("downloads") or {}).get("primary") or {}
        assert isinstance(downloads.get("transcript"), dict)
        artifacts_off = ((st.get("state") or {}).get("artifacts") or [])
        report_art = [a for a in artifacts_off if isinstance(a, dict) and a.get("kind") == "transcript_integrity_report"]
        assert report_art, "transcribe run must emit transcript_integrity_report artifact"
        report_path = Path(report_art[-1].get("path"))
        assert report_path.exists()
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert report_payload.get("ok") is True

        trs = await c.get(f"/api/sessions/{sid}/transcripts")
        assert trs.status_code == 200
        rows = (trs.json().get("transcripts") or [])
        assert rows
        off_rows = [r for r in rows if str(r.get("run_id") or "") == run_id_off]
        assert off_rows
        off_tv = off_rows[0]
        assert off_tv.get("diarization_enabled") is False
        off_tv_id = str(off_tv.get("transcript_version_id") or "")
        assert off_tv_id

        off_payload_resp = await c.get(f"/api/transcripts/{off_tv_id}")
        assert off_payload_resp.status_code == 200
        off_segments = (((off_payload_resp.json() or {}).get("transcript") or {}).get("segments") or [])
        assert off_segments
        assert all(not bool((s or {}).get("speaker")) for s in off_segments if isinstance(s, dict))

        tr2 = await c.post(
            "/api/transcribe",
            json={"session_id": sid, "mode": "meeting", "diarization_enabled": True},
        )
        assert tr2.status_code == 200
        run_id_on = tr2.json()["run_id"]

        for _ in range(80):
            st2 = (await c.get(f"/api/runs/{run_id_on}")).json()
            status2 = ((st2.get("state") or {}).get("status") or "").lower()
            if status2 in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.05)

        st2 = (await c.get(f"/api/runs/{run_id_on}")).json()
        assert ((st2.get("state") or {}).get("status") or "").lower() == "succeeded"

        trs2 = await c.get(f"/api/sessions/{sid}/transcripts")
        assert trs2.status_code == 200
        rows2 = (trs2.json().get("transcripts") or [])
        on_rows = [r for r in rows2 if str(r.get("run_id") or "") == run_id_on]
        assert on_rows
        on_tv = on_rows[0]
        assert on_tv.get("diarization_enabled") is True
        on_tv_id = str(on_tv.get("transcript_version_id") or "")
        assert on_tv_id

        on_payload_resp = await c.get(f"/api/transcripts/{on_tv_id}")
        assert on_payload_resp.status_code == 200
        on_segments = (((on_payload_resp.json() or {}).get("transcript") or {}).get("segments") or [])
        assert any(bool((s or {}).get("speaker")) for s in on_segments if isinstance(s, dict))

        set_off = await c.patch(f"/api/sessions/{sid}/transcripts/active", json={"transcript_version_id": off_tv_id})
        assert set_off.status_code == 200
        set_on = await c.patch(f"/api/sessions/{sid}/transcripts/active", json={"transcript_version_id": on_tv_id})
        assert set_on.status_code == 200
        trs3 = await c.get(f"/api/sessions/{sid}/transcripts")
        rows3 = (trs3.json().get("transcripts") or [])
        active_rows = [r for r in rows3 if r.get("active")]
        assert len(active_rows) == 1
        assert str(active_rows[0].get("transcript_version_id") or "") == on_tv_id
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_cancel_endpoint_writes_cancel_receipt(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        r = await c.post("/api/sessions", json={"mode": "meeting", "title": "cancel"})
        sid = r.json()["session_id"]
        wav_bytes = _gen_wav_bytes(tmp_path)
        up = await c.post(
            f"/api/upload?session_id={sid}",
            content=wav_bytes,
            headers={"x-filename": "test.wav", "content-type": "audio/wav"},
        )
        assert up.status_code == 200

        tr = await c.post("/api/transcribe", json={"session_id": sid, "mode": "meeting"})
        assert tr.status_code == 200
        run_id = tr.json()["run_id"]

        cc = await c.post(f"/api/runs/{run_id}/cancel")
        assert cc.status_code == 200
        cancel_receipt = ((cc.json() or {}).get("cancel_receipt") or "")
        assert cancel_receipt.endswith("/inputs/cancel.json")
        p = Path(cancel_receipt)
        assert p.exists()
        payload = json.loads(p.read_text(encoding="utf-8"))
        assert payload.get("run_id") == run_id

        # Ensure worker reaches a terminal state before tmp runtime teardown.
        for _ in range(80):
            st = (await c.get(f"/api/runs/{run_id}")).json()
            status = ((st.get("state") or {}).get("status") or "").lower()
            if status in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.05)
    finally:
        await c.aclose()
