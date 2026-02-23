from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.adapters.diarize_pyannote import diarize_pyannote


def _gen_normalized(run_dir: Path) -> None:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not installed")
    p = run_dir / "artifacts" / "normalized.wav"
    p.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(p)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def test_diarize_pyannote_writes_v1_json(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "runs" / "run_x"
    _gen_normalized(run_dir)

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)

    art = diarize_pyannote(run_dir)
    out_path = Path(art["path"])
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload.get("engine") in ("stub", "pyannote")
