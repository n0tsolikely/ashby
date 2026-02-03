from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.template_registry import load_system_template_text, validate_template
from ashby.modules.meetings.render.speaker_overlay import apply_speaker_map_to_transcript_text


def render_formalized_md(
    run_dir: Path,
    *,
    mode: str,
    template_id: str,
    transcript_path: Optional[Path],
    speaker_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    QUEST_021 v1: deterministic formalized markdown renderer.
    - Uses system template text as the top prompt/rules block.
    - Embeds the transcript artifact verbatim under a Transcript section.
    """
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    tv = validate_template(mode, template_id)
    if not tv.ok:
        raise ValueError(tv.message or "Invalid mode/template.")

    tmpl = load_system_template_text(mode, template_id).strip()

    transcript_txt = ""
    if transcript_path and transcript_path.exists():
        transcript_txt = transcript_path.read_text(encoding="utf-8").strip()
        if speaker_map:
            transcript_txt = apply_speaker_map_to_transcript_text(transcript_txt, speaker_map)

    out_path = artifacts_dir / "formalized.md"
    if not out_path.exists():
        parts = []
        parts.append("# Stuart v1 — Formalized Output\n")
        parts.append("## System Template\n")
        parts.append(tmpl + "\n")
        parts.append("## Transcript\n")
        if transcript_txt:
            parts.append("```text\n" + transcript_txt + "\n```\n")
        else:
            parts.append("_No transcript artifact found._\n")
        out_path.write_text("\n".join(parts), encoding="utf-8")

    h = sha256_file(out_path)
    return {
        "kind": "formalized_md",
        "path": str(out_path),
        "sha256": h,
        "mime": "text/markdown",
        "created_ts": time.time(),
        "mode": tv.mode_canonical,
        "template_id": tv.template_id,
    }
