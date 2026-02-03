from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from ashby.modules.meetings.hashing import sha256_file


def transcribe_stub(run_dir: Path) -> Dict[str, Any]:
    """
    QUEST_020 (v1 stub): write a transcript artifact.
    Real ASR comes later. This just establishes artifact plumbing + evidence trail.
    """
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    out_path = artifacts_dir / "transcript.txt"
    if not out_path.exists():
        # Include speaker labels so speaker overlay + extract-only flows are testable.
        out_path.write_text(
            "STUART V1 TRANSCRIPT (stub)\n"
            "This is a placeholder transcript artifact.\n\n"
            "SPEAKER_00: Hello, this is a sample speaker line.\n"
            "SPEAKER_01: And this is another speaker line.\n"
            "SPEAKER_01: I made kimchi yesterday and it was spicy.\n"
            "SPEAKER_00: Second line from speaker 00 for extraction tests.\n",
            encoding="utf-8",
        )

    h = sha256_file(out_path)
    return {
        "kind": "transcript",
        "path": str(out_path),
        "sha256": h,
        "mime": "text/plain",
        "created_ts": time.time(),
    }
