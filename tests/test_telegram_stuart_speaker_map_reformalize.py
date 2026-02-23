import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.interfaces.telegram.stuart_runner import (
    run_default_pipeline,
    telegram_set_speaker_map,
    telegram_reformalize_minimal,
)
from ashby.modules.meetings.schemas.run_request import RunRequest


def _make_sine_wav(path: Path, *, seconds: float = 0.25) -> None:
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
def test_telegram_minimal_speaker_map_then_reformalize_returns_pdf(tmp_path, monkeypatch):
    # Isolate runtime writes.
    runtime = tmp_path / "StuartRuntime"
    monkeypatch.setenv("STUART_ROOT", str(runtime))

    wav = tmp_path / "tone.wav"
    _make_sine_wav(wav)

    rr = RunRequest.from_dict({"mode": "meeting", "speakers": 2})
    first = run_default_pipeline(local_path=str(wav), source_kind="audio", run_request=rr)
    assert first.get("ok") is True

    session_id = first.get("session_id")
    source_run_id = first.get("run_id")
    assert isinstance(session_id, str) and session_id.startswith("ses_")
    assert isinstance(source_run_id, str) and source_run_id.startswith("run_")

    pdf1 = first.get("pdf_path")
    assert isinstance(pdf1, str) and pdf1.endswith("minutes.pdf")
    assert Path(pdf1).exists()

    # 1) Set mapping (supports multiple lines; merges with existing mapping if any)
    mapped = telegram_set_speaker_map(
        session_id=session_id,
        mapping_text="SPEAKER_00 is Greg\nSPEAKER_01 is Anna",
    )
    assert mapped.get("ok") is True
    overlay = mapped.get("overlay")
    assert isinstance(overlay, dict)
    assert (overlay.get("mapping") or {}).get("SPEAKER_00") == "Greg"
    assert (overlay.get("mapping") or {}).get("SPEAKER_01") == "Anna"

    # 2) Re-formalize without retranscribing (reuse_run_id)
    rerun = telegram_reformalize_minimal(
        session_id=session_id,
        source_run_id=source_run_id,
        run_request=rr,
    )
    assert rerun.get("ok") is True
    new_run_id = rerun.get("run_id")
    assert isinstance(new_run_id, str) and new_run_id.startswith("run_")
    assert new_run_id != source_run_id

    pdf2 = rerun.get("pdf_path")
    assert isinstance(pdf2, str) and pdf2.endswith("minutes.pdf")
    assert Path(pdf2).exists()

    # Evidence that we actually reused transcript substrate (QUEST_070 behavior):
    # The rerender run must have a reuse receipt.
    receipt = runtime / "runs" / new_run_id / "inputs" / "reused_transcript.json"
    assert receipt.exists()
