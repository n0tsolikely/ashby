from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

from ashby.modules.meetings.hashing import sha256_file


def diarize_stub(run_dir: Path) -> Dict[str, Any]:
    """
    QUEST_020 (v1 stub): write diarization segments artifact.
    Real diarization comes later. This establishes the artifact contract.
    """
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    out_path = artifacts_dir / "diarization_segments.json"
    if not out_path.exists():
        payload = {
            "version": 1,
            "segments": [],
            "note": "stub diarization (no model wired yet)",
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    h = sha256_file(out_path)
    return {
        "kind": "diarization_segments",
        "path": str(out_path),
        "sha256": h,
        "mime": "application/json",
        "created_ts": time.time(),
    }
