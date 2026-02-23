from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.overlays import create_speaker_map_overlay
from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.session_state import set_active_speaker_overlay
from ashby.modules.meetings.store import add_contribution, create_run, create_session, get_run_state


def _gen_wav(path: Path) -> None:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not installed")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def test_create_speaker_map_overlay_returns_required_metadata(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    mapping = {"SPEAKER_00": "Greg"}
    ovr = create_speaker_map_overlay(ses, mapping)

    assert isinstance(ovr.get("overlay_id"), str) and ovr["overlay_id"]
    assert isinstance(ovr.get("path"), str) and ovr["path"]
    assert isinstance(ovr.get("sha256"), str) and len(ovr["sha256"]) == 64
    assert isinstance(ovr.get("created_ts"), float)
    assert ovr.get("mapping") == mapping

    # File should exist at the returned path.
    assert Path(ovr["path"]).exists()


def test_run_manifest_records_active_speaker_map_overlay(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    # Contribution is required for job_runner's input resolver.
    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    ovr = create_speaker_map_overlay(ses, {"SPEAKER_00": "Greg"})
    set_active_speaker_overlay(ses, ovr["overlay_id"])

    run_id = create_run(session_id=ses, plan={"steps": []})

    res = run_job(run_id)
    assert res.ok is True

    state = get_run_state(run_id)
    arts = [a for a in state.get("artifacts", []) if isinstance(a, dict) and a.get("kind") == "speaker_map_overlay_active"]
    assert arts, "Expected run.json to record the active speaker overlay"

    a0 = arts[0]
    assert a0.get("overlay_id") == ovr["overlay_id"]
    assert a0.get("sha256") == ovr["sha256"]
