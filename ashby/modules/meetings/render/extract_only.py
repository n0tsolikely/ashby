from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.render.speaker_overlay import apply_speaker_map_to_transcript_text


def extract_only_by_speaker(
    *,
    out_dir: Path,
    transcript_path: Path,
    speaker_label: str,
    speaker_name: Optional[str] = None,
    speaker_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Extract "only what X said" from a transcript.

    V1 citations are simple line anchors (line numbers) into transcript.txt.
    This is a derived artifact; it never mutates transcript.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = transcript_path.read_text(encoding="utf-8")
    # Apply mapping for display (optional), but matching is done by label.
    display_txt = raw
    if speaker_map:
        display_txt = apply_speaker_map_to_transcript_text(raw, speaker_map)

    citations: List[Dict[str, Any]] = []
    display_lines = display_txt.splitlines()

    # We match against raw lines for label stability.
    raw_lines = raw.splitlines()
    for idx, line in enumerate(raw_lines, start=1):
        if line.startswith(f"{speaker_label}:"):
            # Use display line for nicer speaker name (if applied)
            display_line = display_lines[idx - 1] if idx - 1 < len(display_lines) else line
            text = display_line.split(":", 1)[1].strip() if ":" in display_line else display_line.strip()
            citations.append(
                {
                    "line": idx,
                    "speaker_label": speaker_label,
                    "speaker": speaker_name or speaker_label,
                    "text": text,
                }
            )

    payload = {
        "version": 1,
        "kind": "extract_only",
        "speaker_label": speaker_label,
        "speaker": speaker_name or speaker_label,
        "citations": citations,
        "notes": "v1 citations are transcript.txt line anchors",
    }

    json_path = out_dir / "extract_only.json"
    md_path = out_dir / "extract_only.md"

    if not json_path.exists():
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not md_path.exists():
        lines = [f"# Extract Only — {payload['speaker']}\n", ""]
        for c in citations:
            lines.append(f"- [L{c['line']}] {c['text']}")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "kind": "extract_only",
        "paths": {
            "json": str(json_path),
            "md": str(md_path),
        },
        "sha256": {
            "json": sha256_file(json_path),
            "md": sha256_file(md_path),
        },
        "created_ts": time.time(),
        "count": len(citations),
    }
