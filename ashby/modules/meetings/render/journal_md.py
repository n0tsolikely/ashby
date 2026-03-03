from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.render.citations import format_citations, load_segments_by_id
from ashby.modules.meetings.schemas.journal_v1 import validate_journal_v1

_EMPTY_PLACEHOLDER = "_No entries._"


def _sort_items(items: Any, key: str) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    def _k(d: Any) -> str:
        if not isinstance(d, dict):
            return ""
        v = d.get(key)
        return "" if v is None else str(v)

    return sorted([d for d in items if isinstance(d, dict)], key=_k)


def _render_flags(payload: Dict[str, Any]) -> tuple[bool, bool]:
    include_citations = payload.get("include_citations")
    show_empty_sections = payload.get("show_empty_sections")
    return (
        bool(include_citations) if isinstance(include_citations, bool) else False,
        bool(show_empty_sections) if isinstance(show_empty_sections, bool) else False,
    )


def _citations_text(citations: Any, *, segs_by_id: Dict[int, Dict[str, Any]], include_citations: bool) -> str:
    if not include_citations:
        return ""
    return format_citations(citations, segs_by_id=segs_by_id)


def render_journal_md(run_dir: Path) -> Dict[str, Any]:
    """Render artifacts/journal.json → artifacts/journal.md (deterministic).

    - Stable headings + stable ordering (sorted by *_id where applicable)
    - Citation tokens visible (segment_id + timestamps; e.g., [S12@00:03:12–00:03:19])
      for key points + action items (and sections if present)
    - No-overwrite: refuses if journal.md already exists
    """
    artifacts = run_dir / "artifacts"
    in_path = artifacts / "journal.json"
    out_path = artifacts / "journal.md"

    if not in_path.exists():
        raise FileNotFoundError(f"Missing journal.json: {in_path}")
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite journal.md: {out_path}")

    payload = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("journal.json must be a JSON object")

    validate_journal_v1(payload)

    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    title = str(header.get("title") or "Journal Entry")
    template_id = str(header.get("template_id") or "")
    retention = str(header.get("retention") or "")
    mode = str(header.get("mode") or "journal")

    segs_by_id = load_segments_by_id(run_dir, mode=mode)
    include_citations, show_empty_sections = _render_flags(payload)

    parts: List[str] = []
    parts.append(f"# {title}")
    parts.append("")
    parts.append("## Metadata")
    parts.append(f"- session_id: `{payload.get('session_id')}`")
    parts.append(f"- run_id: `{payload.get('run_id')}`")
    if template_id:
        parts.append(f"- template_id: `{template_id}`")
    if retention:
        parts.append(f"- retention: `{retention}`")
    if "created_ts" in header:
        try:
            parts.append(f"- created_ts: `{float(header.get('created_ts'))}`")
        except Exception:
            pass
    parts.append("")

    mood = payload.get("mood")
    if isinstance(mood, str) and mood.strip():
        parts.append("## Mood")
        parts.append(mood.strip())
        parts.append("")

    sections = _sort_items(payload.get("narrative_sections"), "section_id")
    if sections or show_empty_sections:
        parts.append("## Narrative")
    if sections:
        for s in sections:
            sid = str(s.get("section_id") or "")
            stitle = str(s.get("title") or sid or "Section")
            text = str(s.get("text") or "").strip()
            parts.append(f"### {stitle}")
            if text:
                parts.append(text)
            else:
                parts.append(_EMPTY_PLACEHOLDER)
            cite_txt = _citations_text(s.get("citations"), segs_by_id=segs_by_id, include_citations=include_citations).strip()
            if cite_txt:
                parts.append(cite_txt)
            parts.append("")
    elif show_empty_sections:
        parts.append(_EMPTY_PLACEHOLDER)
        parts.append("")
    if sections or show_empty_sections:
        parts.append("")

    # Key points
    kps = _sort_items(payload.get("key_points"), "point_id")
    if kps or show_empty_sections:
        parts.append("## Key Points")
        if not kps:
            parts.append(_EMPTY_PLACEHOLDER)
        else:
            for kp in kps:
                pid = str(kp.get("point_id") or "")
                text = str(kp.get("text") or "").strip()
                parts.append(
                    f"- ({pid}) {text}{_citations_text(kp.get('citations'), segs_by_id=segs_by_id, include_citations=include_citations)}"
                )
        parts.append("")

    # Feelings
    fl = payload.get("feelings")
    feelings = [x for x in fl if isinstance(x, dict)] if isinstance(fl, list) else []
    has_feelings = any(str(f.get("text") or "").strip() for f in feelings)
    if has_feelings or show_empty_sections:
        parts.append("## Feelings")
        if not has_feelings:
            parts.append(_EMPTY_PLACEHOLDER)
        else:
            for f in feelings:
                text = str(f.get("text") or "").strip()
                if not text:
                    continue
                parts.append(
                    f"- {text}{_citations_text(f.get('citations'), segs_by_id=segs_by_id, include_citations=include_citations)}"
                )
        parts.append("")

    # Action items
    actions = _sort_items(payload.get("action_items"), "action_id")
    if actions or show_empty_sections:
        parts.append("## Action Items")
    if actions:
        for a in actions:
            aid = str(a.get("action_id") or "")
            text = str(a.get("text") or "").strip()
            assignee = a.get("assignee")
            due = a.get("due_date")
            suffix = []
            if assignee:
                suffix.append(f"assignee={assignee}")
            if due:
                suffix.append(f"due={due}")
            meta = f" ({', '.join(suffix)})" if suffix else ""
            parts.append(
                f"- ({aid}) {text}{meta}{_citations_text(a.get('citations'), segs_by_id=segs_by_id, include_citations=include_citations)}"
            )
    elif show_empty_sections:
        parts.append(_EMPTY_PLACEHOLDER)
    if actions or show_empty_sections:
        parts.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")

    return {
        "kind": "journal_md",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "mime": "text/markdown",
        "created_ts": time.time(),
        "mode": "journal",
        "template_id": template_id,
    }
