from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.adapters.transcribe_faster_whisper import transcribe_faster_whisper_or_stub


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_transcribe_adapter_writes_transcript_json(tmp_path: Path):
    run_dir = tmp_path / "runs" / "run_x"
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    src = run_dir / "artifacts" / "normalized.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(src)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    art = transcribe_faster_whisper_or_stub(run_dir)
    assert art["kind"] == "transcript"

    txt_path = run_dir / "artifacts" / "transcript.txt"
    json_path = run_dir / "artifacts" / "transcript.json"
    assert txt_path.exists()
    assert json_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert "segments" in payload
    assert payload.get("engine") in ("stub", "faster-whisper")

    with pytest.raises(FileExistsError):
        transcribe_faster_whisper_or_stub(run_dir)
