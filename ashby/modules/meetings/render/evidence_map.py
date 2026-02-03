from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

from ashby.modules.meetings.hashing import sha256_file


def build_evidence_map(run_dir: Path) -> Dict[str, Any]:
    """
    QUEST_021 v1: evidence map skeleton.
    Later: claims -> transcript anchors, speaker/time spans, etc.
    """
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    out_path = artifacts_dir / "evidence_map.json"
    if not out_path.exists():
        payload = {
            "version": 1,
            "claims": [],
            "notes": "v1 stub: claims/anchors populated later after real ASR+diarization+alignment",
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    h = sha256_file(out_path)
    return {
        "kind": "evidence_map",
        "path": str(out_path),
        "sha256": h,
        "mime": "application/json",
        "created_ts": time.time(),
    }
