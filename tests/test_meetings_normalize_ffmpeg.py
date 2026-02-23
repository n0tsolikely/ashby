from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.pipeline.normalize import normalize_ffmpeg


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_normalize_ffmpeg_creates_wav(tmp_path: Path):
    src = tmp_path / "in.wav"
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["ffmpeg","-y","-f","lavfi","-i","sine=frequency=1000:duration=0.2", str(src)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    art = normalize_ffmpeg(run_dir, src)
    assert art["kind"] == "normalized_audio"
    p = Path(art["path"])
    assert p.exists()
    assert p.name == "normalized.wav"
