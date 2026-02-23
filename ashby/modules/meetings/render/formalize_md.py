from __future__ import annotations

import time
from pathlib import Path
import json

def _load_transcript_lines(run_dir: Path, *, mode: str) -> list[str]:
    """Return transcript lines for rendering.

    Preference:
    - meeting: aligned_transcript.json (speaker-tagged) if present
    - else: transcript.json (speaker-tagged) if present
    - else: transcript.txt (raw) if present
    - else: [] (no transcript)
    """
    artifacts = run_dir / "artifacts"
    ajson = artifacts / "aligned_transcript.json"
    tjson = artifacts / "transcript.json"
    ttxt = artifacts / "transcript.txt"

    if mode == "meeting" and ajson.exists():
        try:
            payload = json.loads(ajson.read_text(encoding="utf-8"))
            lines = []
            for s in payload.get("segments") or []:
                spk = (s.get("speaker") or "SPEAKER_00")
                text = (s.get("text") or "").strip()
                if text:
                    lines.append(f"{spk}: {text}")
            return lines
        except Exception:
            pass

    if tjson.exists():
        try:
            payload = json.loads(tjson.read_text(encoding="utf-8"))
            lines = []
            for s in payload.get("segments") or []:
                spk = (s.get("speaker") or "SPEAKER_00")
                text = (s.get("text") or "").strip()
                if text:
                    lines.append(f"{spk}: {text}")
            return lines
        except Exception:
            pass

    if ttxt.exists():
        return [ln.strip() for ln in ttxt.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]

    return []

from typing import Any, Dict, List, Tuple

def _load_segments_for_render(run_dir: Path, *, mode: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Return (source_name, segments) for rendering.

    Rule:
    - meeting mode prefers aligned_transcript.json if present
    - journal mode uses transcript.json
    - fallback to transcript.txt as SPEAKER_00 lines
    """
    ajson = run_dir / "artifacts" / "aligned_transcript.json"
    tjson = run_dir / "artifacts" / "transcript.json"
    if mode == "meeting" and ajson.exists():
        payload = json.loads(ajson.read_text(encoding="utf-8"))
        return ("aligned_transcript.json", payload.get("segments") or [])
    if tjson.exists():
        payload = json.loads(tjson.read_text(encoding="utf-8"))
        return ("transcript.json", payload.get("segments") or [])
    ttxt = run_dir / "artifacts" / "transcript.txt"
    segs: List[Dict[str, Any]] = []
    if ttxt.exists():
        for i, line in enumerate(ttxt.read_text(encoding="utf-8", errors="replace").splitlines()):
            segs.append({"segment_id": i, "start_ms": 0, "end_ms": 0, "speaker": "SPEAKER_00", "text": line.strip()})
    return ("transcript.txt", segs)

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

    # QUEST_039: if no transcript_path provided, load from canonical artifacts
    if not transcript_txt:
        lines = _load_transcript_lines(run_dir, mode=mode)
        if lines:
            transcript_txt = "\n".join(lines).strip()
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
