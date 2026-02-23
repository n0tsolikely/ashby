from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from ashby.modules.meetings.store import sha256_file


def normalize_ffmpeg(run_dir: Path, source_path: Path) -> Dict[str, Any]:
    """Normalize input to 16kHz mono wav.

    Writes (write-once):
      run_dir/artifacts/normalized.wav
    """
    # NOTE: We keep the contract name (normalize_ffmpeg) but allow a fast-path for
    # local test runs to keep the suite snappy in constrained environments.
    # This is opt-in via env var and preserves production behavior by default.
    fast_tests = (os.environ.get("ASHBY_FAST_TESTS") or "").strip().lower() in {"1", "true", "yes"}

    ffmpeg = None if fast_tests else shutil.which("ffmpeg")
    if not ffmpeg and not fast_tests:
        raise RuntimeError("ffmpeg not found on PATH (required for normalize stage)")

    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    out_path = artifacts_dir / "normalized.wav"
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite normalized audio: {out_path}")

    if fast_tests:
        # Fast tests mode: copy bytes verbatim. Downstream stages in LOCAL_ONLY
        # treat audio as opaque unless real ASR/diarization engines are enabled.
        out_path.write_bytes(source_path.read_bytes())
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-i", str(source_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-f", "wav",
            str(out_path),
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"ffmpeg failed (rc={p.returncode}): {p.stderr}")

    return {
        "kind": "normalized_audio",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "created_ts": time.time(),
    }
