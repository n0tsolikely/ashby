from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.schemas.evidence_map_v2 import validate_evidence_map_v2
from ashby.modules.meetings.store import sha256_file


def _load_transcript_payload(run_dir: Path, *, mode: str) -> Tuple[str, str, List[Dict[str, Any]], Optional[str]]:
    """Load transcript segments for evidence anchoring.

    Preference:
    - meeting: aligned_transcript.json if present
    - else: transcript.json if present
    - else: transcript.txt lines as SPEAKER_00 (no timestamps)

    Returns (session_id, run_id, segments, transcript_version_id).
    """
    artifacts = run_dir / "artifacts"
    ajson = artifacts / "aligned_transcript.json"
    tjson = artifacts / "transcript.json"
    ttxt = artifacts / "transcript.txt"

    if mode == "meeting" and ajson.exists():
        payload = json.loads(ajson.read_text(encoding="utf-8"))
        return (
            str(payload.get("session_id") or ""),
            # QUEST_070: evidence_map is a derived artifact for the *current* run.
            # Transcript payload run_id may be from a reused source run.
            run_dir.name,
            list(payload.get("segments") or []),
            str(payload.get("transcript_version_id")).strip() if isinstance(payload.get("transcript_version_id"), str) else None,
        )

    if tjson.exists():
        payload = json.loads(tjson.read_text(encoding="utf-8"))
        return (
            str(payload.get("session_id") or ""),
            # QUEST_070: evidence_map is a derived artifact for the *current* run.
            # Transcript payload run_id may be from a reused source run.
            run_dir.name,
            list(payload.get("segments") or []),
            str(payload.get("transcript_version_id")).strip() if isinstance(payload.get("transcript_version_id"), str) else None,
        )

    # Fallback to transcript.txt (no timestamps) — still truthfully anchored by line order.
    segs: List[Dict[str, Any]] = []
    if ttxt.exists():
        for i, line in enumerate(ttxt.read_text(encoding="utf-8", errors="replace").splitlines()):
            s = line.strip()
            if not s:
                continue
            segs.append(
                {
                    "segment_id": int(i),
                    "start_ms": 0,
                    "end_ms": 0,
                    "speaker": "SPEAKER_00",
                    "text": s,
                }
            )
    return ("", run_dir.name, segs, None)


def _segment_index(segs: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for i, s in enumerate(segs):
        try:
            sid = int(s.get("segment_id", i))
        except Exception:
            sid = int(i)
        out[sid] = s
    return out


def _anchor_from_segment(seg: Optional[Dict[str, Any]], *, segment_id: int) -> Dict[str, Any]:
    if not isinstance(seg, dict):
        # Unknown segment => truthful minimal anchor
        return {
            "segment_id": int(segment_id),
            "t_start": 0.0,
            "t_end": 0.0,
            "speaker_label": "SPEAKER_00",
        }

    try:
        t0 = float(seg.get("start_ms", 0)) / 1000.0
    except Exception:
        t0 = 0.0
    try:
        t1 = float(seg.get("end_ms", 0)) / 1000.0
    except Exception:
        t1 = 0.0

    spk = seg.get("speaker")
    speaker_label = str(spk or "SPEAKER_00")

    return {
        "segment_id": int(segment_id),
        "t_start": float(t0),
        "t_end": float(t1),
        "speaker_label": speaker_label,
    }


def _anchors_from_citations(citations: Any, segs_by_id: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    anchors: List[Dict[str, Any]] = []
    if not isinstance(citations, list):
        return anchors

    for c in citations:
        if not isinstance(c, dict) or "segment_id" not in c:
            continue
        try:
            sid = int(c["segment_id"])
        except Exception:
            continue
        anchors.append(_anchor_from_segment(segs_by_id.get(sid), segment_id=sid))
    return anchors


def _claims_from_minutes(minutes_payload: Dict[str, Any], segs_by_id: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []

    for t in minutes_payload.get("topics") or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("topic_id") or "")
        claims.append(
            {
                "claim_id": f"minutes.topic.{tid}" if tid else "minutes.topic",
                "claim_type": "minutes.topic",
                "claim_text": str(t.get("summary") or ""),
                "title": str(t.get("title") or ""),
                "source": {"artifact": "minutes.json", "item_type": "topic", "item_id": tid},
                "anchors": _anchors_from_citations(t.get("citations"), segs_by_id),
            }
        )

    for d in minutes_payload.get("decisions") or []:
        if not isinstance(d, dict):
            continue
        did = str(d.get("decision_id") or "")
        claims.append(
            {
                "claim_id": f"minutes.decision.{did}" if did else "minutes.decision",
                "claim_type": "minutes.decision",
                "claim_text": str(d.get("text") or ""),
                "source": {"artifact": "minutes.json", "item_type": "decision", "item_id": did},
                "anchors": _anchors_from_citations(d.get("citations"), segs_by_id),
            }
        )

    for a in minutes_payload.get("action_items") or []:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("action_id") or "")
        claims.append(
            {
                "claim_id": f"minutes.action_item.{aid}" if aid else "minutes.action_item",
                "claim_type": "minutes.action_item",
                "claim_text": str(a.get("text") or ""),
                "source": {"artifact": "minutes.json", "item_type": "action_item", "item_id": aid},
                "anchors": _anchors_from_citations(a.get("citations"), segs_by_id),
            }
        )

    for n in minutes_payload.get("notes") or []:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("note_id") or "")
        claims.append(
            {
                "claim_id": f"minutes.note.{nid}" if nid else "minutes.note",
                "claim_type": "minutes.note",
                "claim_text": str(n.get("text") or ""),
                "source": {"artifact": "minutes.json", "item_type": "note", "item_id": nid},
                "anchors": _anchors_from_citations(n.get("citations"), segs_by_id),
            }
        )

    for q in minutes_payload.get("open_questions") or []:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("question_id") or "")
        claims.append(
            {
                "claim_id": f"minutes.open_question.{qid}" if qid else "minutes.open_question",
                "claim_type": "minutes.open_question",
                "claim_text": str(q.get("text") or ""),
                "source": {"artifact": "minutes.json", "item_type": "open_question", "item_id": qid},
                "anchors": _anchors_from_citations(q.get("citations"), segs_by_id),
            }
        )

    return claims


def _claims_from_journal(journal_payload: Dict[str, Any], segs_by_id: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []

    for s in journal_payload.get("narrative_sections") or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("section_id") or "")
        claims.append(
            {
                "claim_id": f"journal.narrative.{sid}" if sid else "journal.narrative",
                "claim_type": "journal.narrative",
                "claim_text": str(s.get("text") or ""),
                "title": str(s.get("title") or ""),
                "source": {"artifact": "journal.json", "item_type": "narrative", "item_id": sid},
                "anchors": _anchors_from_citations(s.get("citations"), segs_by_id),
            }
        )

    for kp in journal_payload.get("key_points") or []:
        if not isinstance(kp, dict):
            continue
        pid = str(kp.get("point_id") or "")
        claims.append(
            {
                "claim_id": f"journal.key_point.{pid}" if pid else "journal.key_point",
                "claim_type": "journal.key_point",
                "claim_text": str(kp.get("text") or ""),
                "source": {"artifact": "journal.json", "item_type": "key_point", "item_id": pid},
                "anchors": _anchors_from_citations(kp.get("citations"), segs_by_id),
            }
        )

    for a in journal_payload.get("action_items") or []:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("action_id") or "")
        claims.append(
            {
                "claim_id": f"journal.action_item.{aid}" if aid else "journal.action_item",
                "claim_type": "journal.action_item",
                "claim_text": str(a.get("text") or ""),
                "source": {"artifact": "journal.json", "item_type": "action_item", "item_id": aid},
                "anchors": _anchors_from_citations(a.get("citations"), segs_by_id),
            }
        )

    for f in journal_payload.get("feelings") or []:
        if not isinstance(f, dict):
            continue
        txt = str(f.get("text") or "")
        # Feelings may omit citations; still represented (anchors may be empty)
        claims.append(
            {
                "claim_id": "journal.feeling",
                "claim_type": "journal.feeling",
                "claim_text": txt,
                "source": {"artifact": "journal.json", "item_type": "feeling", "item_id": ""},
                "anchors": _anchors_from_citations(f.get("citations"), segs_by_id),
            }
        )

    return claims


def _fallback_transcript_claim(segs: List[Dict[str, Any]], segs_by_id: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    # Minimal truthful claim when no minutes/journal artifacts exist.
    if not segs:
        anchors: List[Dict[str, Any]] = []
    else:
        first = segs[0]
        last = segs[-1]
        anchors = []
        for s in (first, last) if last is not first else (first,):
            try:
                sid = int(s.get("segment_id", 0))
            except Exception:
                sid = 0
            anchors.append(_anchor_from_segment(segs_by_id.get(sid), segment_id=sid))

    return {
        "claim_id": "transcript",
        "claim_type": "transcript.section",
        "claim_text": "Transcript section",
        "anchors": anchors,
    }


def build_evidence_map(run_dir: Path) -> Dict[str, Any]:
    """Build and write evidence_map.json deterministically (v2).

    V2:
    - claim-level anchors
    - claims derived from minutes.json or journal.json
    - anchors resolve to transcript segments (segment_id + time range + speaker label)

    Naming:
    - Keep artifact name stable: artifacts/evidence_map.json
    - Version is inside file.
    """

    out_path = run_dir / "artifacts" / "evidence_map.json"
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite evidence_map: {out_path}")

    # Attempt to infer mode from run manifest if available; fallback meeting
    mode = "meeting"
    run_json = run_dir / "run.json"
    if run_json.exists():
        try:
            run_state = json.loads(run_json.read_text(encoding="utf-8"))
            mode = str(run_state.get("mode") or mode)
        except Exception:
            pass

    session_id_t, run_id_t, segs, transcript_version_id = _load_transcript_payload(run_dir, mode=mode)
    segs_by_id = _segment_index(segs)

    artifacts = run_dir / "artifacts"

    claims: List[Dict[str, Any]] = []
    session_id = session_id_t
    run_id = run_id_t

    if mode == "meeting":
        minutes_path = artifacts / "minutes.json"
        if minutes_path.exists():
            minutes_payload = json.loads(minutes_path.read_text(encoding="utf-8"))
            session_id = str(minutes_payload.get("session_id") or session_id)
            run_id = str(minutes_payload.get("run_id") or run_id)
            claims = _claims_from_minutes(minutes_payload, segs_by_id)

    elif mode == "journal":
        journal_path = artifacts / "journal.json"
        if journal_path.exists():
            journal_payload = json.loads(journal_path.read_text(encoding="utf-8"))
            session_id = str(journal_payload.get("session_id") or session_id)
            run_id = str(journal_payload.get("run_id") or run_id)
            claims = _claims_from_journal(journal_payload, segs_by_id)

    if not claims:
        claims = [_fallback_transcript_claim(segs, segs_by_id)]

    payload: Dict[str, Any] = {
        "version": 2,
        "session_id": session_id,
        "run_id": run_id,
        "mode": mode,
        "claims": claims,
    }
    if transcript_version_id:
        payload["transcript_version_id"] = transcript_version_id

    validate_evidence_map_v2(payload)
    dump_json(out_path, payload, write_once=True)

    return {
        "kind": "evidence_map",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "created_ts": time.time(),
        "version": 2,
    }
