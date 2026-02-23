from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict

from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.hashing import sha256_file


_SPEAKER_RE = re.compile(r"^(SPEAKER_\d+):\s*(.*)$")


def transcribe_stub(run_dir: Path) -> Dict[str, Any]:
    """
    QUEST_020 (v1 stub): write a transcript artifact.
    Real ASR comes later. This just establishes artifact plumbing + evidence trail.
    """
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    out_path = artifacts_dir / "transcript.txt"
    json_path = artifacts_dir / "transcript.json"
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

    # QUEST_057: ensure transcript.json exists so indexing + formalize never rely on brittle .txt parsing.
    # We treat timestamps as unknown for the stub: start_ms/end_ms = 0.
    if not json_path.exists():
        segments = []
        for line in out_path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _SPEAKER_RE.match(line.strip())
            if not m:
                continue
            speaker = m.group(1).strip().upper()
            text = m.group(2).strip()
            if not text:
                continue
            segments.append(
                {
                    "segment_id": len(segments),
                    "start_ms": 0,
                    "end_ms": 0,
                    "speaker": speaker,
                    "text": text,
                }
            )

        payload = {
            "version": 1,
            "session_id": "",
            "run_id": run_dir.name,
            "segments": segments,
            "engine": "stub",
        }
        dump_json(json_path, payload, write_once=True)

    h = sha256_file(out_path)
    return {
        "kind": "transcript",
        "path": str(out_path),
        "sha256": h,
        "mime": "text/plain",
        "created_ts": time.time(),
        "json_path": str(json_path),
    }
