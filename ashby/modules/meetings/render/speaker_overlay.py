from __future__ import annotations

from typing import Dict


def apply_speaker_map_to_transcript_text(transcript_text: str, mapping: Dict[str, str]) -> str:
    """Apply SPEAKER_XX -> Name substitution for display-only views.

    This is a derived view. Ground truth transcript artifacts remain unchanged.
    """
    if not transcript_text or not mapping:
        return transcript_text

    out_lines = []
    for line in transcript_text.splitlines():
        # Common prefix: "SPEAKER_00: ..."
        if ":" in line:
            head, rest = line.split(":", 1)
            key = head.strip()
            if key in mapping:
                out_lines.append(f"{mapping[key]}:{rest}")
                continue
        out_lines.append(line)
    return "\n".join(out_lines)
