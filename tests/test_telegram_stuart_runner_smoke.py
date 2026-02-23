import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.interfaces.telegram.stuart_runner import run_default_pipeline
from ashby.modules.meetings.schemas.run_request import RunRequest


def _make_sine_wav(path, *, seconds: float = 0.25) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg missing")

    # Generate a tiny deterministic mono WAV.
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing")
def test_telegram_runner_returns_primary_pdf_paths(tmp_path, monkeypatch):
    # Isolate runtime writes.
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "StuartRuntime"))

    wav = tmp_path / "tone.wav"
    _make_sine_wav(wav)

    # Meeting => minutes.pdf
    out_m = run_default_pipeline(
        local_path=str(wav),
        source_kind="audio",
        run_request=RunRequest.from_dict({"mode": "meeting", "speakers": 2}),
    )
    assert out_m.get("ok") is True
    pdf_m = out_m.get("pdf_path")
    assert isinstance(pdf_m, str) and pdf_m.endswith("minutes.pdf")
    assert (tmp_path / "StuartRuntime").exists()  # sanity
    assert Path(pdf_m).exists()

    # Journal => journal.pdf
    out_j = run_default_pipeline(
        local_path=str(wav),
        source_kind="audio",
        run_request=RunRequest.from_dict({"mode": "journal", "speakers": "auto"}),
    )
    assert out_j.get("ok") is True
    pdf_j = out_j.get("pdf_path")
    assert isinstance(pdf_j, str) and pdf_j.endswith("journal.pdf")
    assert Path(pdf_j).exists()
