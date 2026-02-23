from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.render.citations import format_citations, load_segments_by_id
from ashby.modules.meetings.render.speaker_overlay import apply_speaker_map_to_transcript_text
from ashby.modules.meetings.schemas.minutes_v1 import validate_minutes_v1


def _sort_items(items: Any, key: str) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    def _k(d: Any) -> str:
        if not isinstance(d, dict):
            return ""
        v = d.get(key)
        return "" if v is None else str(v)

    return sorted([d for d in items if isinstance(d, dict)], key=_k)


def _load_speaker_map_for_run(run_dir: Path) -> Dict[str, str]:
    """Load an effective speaker label → display name mapping for *this run*.

    Determinism rule:
    - Prefer the overlay snapshot recorded in this run's run.json artifacts.
      (speaker_map_overlay includes mapping inline; speaker_map_overlay_active points to an overlay file.)
    - If run.json is missing or no overlay is present, return {}.

    Note: Keys are normalized to upper-case labels (e.g., SPEAKER_00).
    """
    run_json = run_dir / "run.json"
    if not run_json.exists():
        return {}

    try:
        st = json.loads(run_json.read_text(encoding="utf-8"))
    except Exception:
        return {}

    arts = st.get("artifacts") if isinstance(st, dict) else None
    if not isinstance(arts, list):
        return {}

    def _coerce_map(mraw: Any) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not isinstance(mraw, dict):
            return out
        for k, v in mraw.items():
            if not isinstance(k, str) or not isinstance(v, str):
                continue
            kk = k.strip().upper()
            vv = v.strip()
            if kk and vv:
                out[kk] = vv
        return out

    # Prefer an explicit mapping captured in this run.
    for a in reversed(arts):
        if not isinstance(a, dict):
            continue
        if a.get("kind") != "speaker_map_overlay":
            continue
        m = _coerce_map(a.get("mapping"))
        if m:
            return m
        # Fallback: load overlay file referenced by path
        p = a.get("path")
        if isinstance(p, str) and p:
            try:
                ovr = json.loads(Path(p).read_text(encoding="utf-8"))
                m2 = _coerce_map(ovr.get("mapping"))
                if m2:
                    return m2
            except Exception:
                return {}

    # Fallback: active overlay reference at run start.
    for a in reversed(arts):
        if not isinstance(a, dict):
            continue
        if a.get("kind") != "speaker_map_overlay_active":
            continue
        p = a.get("path")
        if isinstance(p, str) and p:
            try:
                ovr = json.loads(Path(p).read_text(encoding="utf-8"))
                m = _coerce_map(ovr.get("mapping"))
                if m:
                    return m
            except Exception:
                return {}

    return {}


def _load_diarization_confidence(run_dir: Path) -> float | None:
    """Return diarization confidence if artifacts/diarization.json exists."""
    p = run_dir / "artifacts" / "diarization.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("confidence") is not None:
            return float(d.get("confidence"))
    except Exception:
        return None
    return None



def render_minutes_md(run_dir: Path) -> Dict[str, Any]:
    """Render artifacts/minutes.json → artifacts/minutes.md (deterministic).

    - Stable headings + stable ordering (sorted by *_id where applicable)
    - Citation tokens visible (segment_id + timestamps; e.g., [S12@00:03:12–00:03:19])
    - No-overwrite: refuses if minutes.md already exists
    """
    artifacts = run_dir / "artifacts"
    in_path = artifacts / "minutes.json"
    out_path = artifacts / "minutes.md"

    if not in_path.exists():
        raise FileNotFoundError(f"Missing minutes.json: {in_path}")
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite minutes.md: {out_path}")

    payload = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("minutes.json must be a JSON object")

    validate_minutes_v1(payload)

    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    title = str(header.get("title") or "Meeting Minutes")
    template_id = str(header.get("template_id") or "")
    retention = str(header.get("retention") or "")
    mode = str(header.get("mode") or "meeting")

    segs_by_id = load_segments_by_id(run_dir, mode=mode)

    speaker_map = _load_speaker_map_for_run(run_dir)

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
    diar_conf = _load_diarization_confidence(run_dir)
    if diar_conf is not None:
        parts.append(f"- diarization_confidence: `{diar_conf}`")
        if diar_conf < 0.6:
            parts.append("- speaker_identity_note: diarization confidence is low; speaker attribution may be unreliable.")

    parts.append("")

    # Participants
    parts.append("## Participants")
    participants = _sort_items(payload.get("participants"), "speaker_label")
    if not participants:
        parts.append("_No participants listed._")
    else:
        for p in participants:
            spk = str(p.get("speaker_label") or "")
            dn = str(p.get("display_name") or "")
            if (not dn) and spk:
                dn = speaker_map.get(spk.strip().upper(), "")
            if dn:
                parts.append(f"- `{spk}` → {dn}")
            else:
                parts.append(f"- `{spk}`")
    parts.append("")

    # Topics
    parts.append("## Topics")
    topics = _sort_items(payload.get("topics"), "topic_id")
    if not topics:
        parts.append("_No topics._")
    else:
        for t in topics:
            tid = str(t.get("topic_id") or "")
            ttitle = str(t.get("title") or "")
            summary = str(t.get("summary") or "").strip()
            line = f"- ({tid}) **{ttitle}**"
            if summary:
                line += f": {summary}"
            line += format_citations(t.get("citations"), segs_by_id=segs_by_id)
            parts.append(line)
    parts.append("")

    # Decisions
    parts.append("## Decisions")
    decisions = _sort_items(payload.get("decisions"), "decision_id")
    if not decisions:
        parts.append("No explicit decisions recorded.")
    else:
        for d in decisions:
            did = str(d.get("decision_id") or "")
            text = str(d.get("text") or "").strip()
            if speaker_map:
                text = apply_speaker_map_to_transcript_text(text, speaker_map).strip()
            line = f"- ({did}) {text}{format_citations(d.get('citations'), segs_by_id=segs_by_id)}"
            parts.append(line)
    parts.append("")

    # Action Items
    parts.append("## Action Items")
    actions = _sort_items(payload.get("action_items"), "action_id")
    if not actions:
        parts.append("No action items recorded.")
    else:
        for a in actions:
            aid = str(a.get("action_id") or "")
            text = str(a.get("text") or "").strip()
            assignee = a.get("assignee")
            assignee_display = assignee
            if isinstance(assignee, str):
                k = assignee.strip().upper()
                if speaker_map.get(k):
                    assignee_display = speaker_map.get(k)
            due = a.get("due_date")
            suffix = []
            if assignee_display:
                suffix.append(f"assignee={assignee_display}")
            if due:
                suffix.append(f"due={due}")
            meta = f" ({', '.join(suffix)})" if suffix else ""
            line = f"- ({aid}) {text}{meta}{format_citations(a.get('citations'), segs_by_id=segs_by_id)}"
            parts.append(line)
    parts.append("")

    # Notes
    parts.append("## Notes")
    notes = _sort_items(payload.get("notes"), "note_id")
    if not notes:
        parts.append("_No notes._")
    else:
        for n in notes:
            nid = str(n.get("note_id") or "")
            text = str(n.get("text") or "").strip()
            if speaker_map:
                text = apply_speaker_map_to_transcript_text(text, speaker_map).strip()
            line = f"- ({nid}) {text}{format_citations(n.get('citations'), segs_by_id=segs_by_id)}"
            parts.append(line)
    parts.append("")

    # Open Questions
    parts.append("## Open Questions")
    qs = _sort_items(payload.get("open_questions"), "question_id")
    if not qs:
        parts.append("_No open questions._")
    else:
        for q in qs:
            qid = str(q.get("question_id") or "")
            text = str(q.get("text") or "").strip()
            if speaker_map:
                text = apply_speaker_map_to_transcript_text(text, speaker_map).strip()
            line = f"- ({qid}) {text}{format_citations(q.get('citations'), segs_by_id=segs_by_id)}"
            parts.append(line)
    parts.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")

    return {
        "kind": "minutes_md",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "mime": "text/markdown",
        "created_ts": time.time(),
        "mode": "meeting",
        "template_id": template_id,
    }
