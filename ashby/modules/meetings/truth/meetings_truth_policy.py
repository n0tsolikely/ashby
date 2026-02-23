from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ashby.core.truth.policy import TruthPolicy
from ashby.core.truth.evidence import EvidenceBundle, TruthViolation

from ashby.modules.meetings.schemas.minutes_v1 import validate_minutes_v1
from ashby.modules.meetings.schemas.journal_v1 import validate_journal_v1


_SPEAKER_LABEL_RE = re.compile(r"^SPEAKER_\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class _AnchorRef:
    segment_id: Optional[int]
    where: str


def _coerce_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _iter_minutes_anchor_refs(payload: Dict[str, Any]) -> Iterable[_AnchorRef]:
    def iter_list(section: str, id_key: str) -> Iterable[_AnchorRef]:
        items = payload.get(section)
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            item_id = str(it.get(id_key) or "")
            cites = it.get("citations")
            if not isinstance(cites, list):
                continue
            for c in cites:
                if not isinstance(c, dict):
                    continue
                sid = _coerce_int(c.get("segment_id"))
                yield _AnchorRef(segment_id=sid, where=f"{section}:{item_id}")

    yield from iter_list("topics", "topic_id")
    yield from iter_list("decisions", "decision_id")
    yield from iter_list("action_items", "action_id")
    yield from iter_list("notes", "note_id")
    yield from iter_list("open_questions", "question_id")


def _iter_journal_anchor_refs(payload: Dict[str, Any]) -> Iterable[_AnchorRef]:
    # narrative_sections citations are optional
    sections = payload.get("narrative_sections")
    if isinstance(sections, list):
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            sec_id = str(sec.get("section_id") or "")
            cites = sec.get("citations")
            if not isinstance(cites, list):
                continue
            for c in cites:
                if not isinstance(c, dict):
                    continue
                sid = _coerce_int(c.get("segment_id"))
                yield _AnchorRef(segment_id=sid, where=f"narrative_sections:{sec_id}")

    def iter_list(section: str, id_key: str) -> Iterable[_AnchorRef]:
        items = payload.get(section)
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            item_id = str(it.get(id_key) or "")
            cites = it.get("citations")
            if not isinstance(cites, list):
                continue
            for c in cites:
                if not isinstance(c, dict):
                    continue
                sid = _coerce_int(c.get("segment_id"))
                yield _AnchorRef(segment_id=sid, where=f"{section}:{item_id}")

    yield from iter_list("key_points", "point_id")
    yield from iter_list("action_items", "action_id")

    # feelings citations are optional
    feelings = payload.get("feelings")
    if isinstance(feelings, list):
        for idx, f in enumerate(feelings):
            if not isinstance(f, dict):
                continue
            cites = f.get("citations")
            if not isinstance(cites, list):
                continue
            for c in cites:
                if not isinstance(c, dict):
                    continue
                sid = _coerce_int(c.get("segment_id"))
                yield _AnchorRef(segment_id=sid, where=f"feelings:{idx}")


def _extract_overlay_mapping(evidence: EvidenceBundle) -> Dict[str, str]:
    for a in evidence.artifact_results:
        if a.artifact_type == "meetings_speaker_map_overlay_v1":
            meta = a.metadata or {}
            m = meta.get("mapping")
            if isinstance(m, dict):
                out: Dict[str, str] = {}
                for k, v in m.items():
                    if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                        out[k.strip().upper()] = v.strip()
                return out
    return {}


def _extract_diarization_confidence(evidence: EvidenceBundle) -> Optional[float]:
    for a in evidence.artifact_results:
        if a.artifact_type == "meetings_diarization_v1":
            meta = a.metadata or {}
            v = meta.get("confidence")
            try:
                return float(v) if v is not None else None
            except Exception:
                return None
    return None


def _valid_segment_ids(evidence: EvidenceBundle) -> Set[int]:
    ids: Set[int] = set()
    for c in evidence.citations:
        if c.segment_id is None:
            continue
        try:
            ids.add(int(c.segment_id))
        except Exception:
            continue
    return ids


class MeetingsTruthPolicy(TruthPolicy):
    """Truth policy for Meetings module outputs.

    Scope (SIDE-QUEST_077):
    - Enforce that citations point to existing transcript segments (no phantom anchors).
    - Prevent ungrounded identity claims (names) unless backed by a speaker-map overlay.

    Notes:
    - This policy is intentionally conservative; it blocks rather than silently publish.
    - It is module-local and should not leak into Ashby platform routing.
    """

    policy_id = "meetings_truth_policy_v1"

    # If diarization confidence is below this, identity claims should be treated as uncertain.
    diarization_confidence_warn_threshold: float = 0.6

    def validate(self, draft: str, evidence: EvidenceBundle) -> List[TruthViolation]:
        violations: List[TruthViolation] = []

        try:
            payload = json.loads(draft)
        except Exception as e:
            return [
                TruthViolation(
                    code="DRAFT_NOT_JSON",
                    message=f"draft is not valid JSON: {type(e).__name__}: {e}",
                    evidence_required=False,
                    severity="block",
                )
            ]

        if not isinstance(payload, dict):
            return [
                TruthViolation(
                    code="DRAFT_NOT_OBJECT",
                    message="draft JSON must be an object",
                    evidence_required=False,
                    severity="block",
                )
            ]

        header = _safe_dict(payload.get("header"))
        mode = header.get("mode")
        mode_s = str(mode or "").strip().lower()

        # Validate schema (truth rail)
        try:
            if mode_s == "meeting":
                validate_minutes_v1(payload)
            elif mode_s == "journal":
                validate_journal_v1(payload)
            else:
                raise ValueError(f"unsupported mode: {mode_s!r}")
        except Exception as e:
            return [
                TruthViolation(
                    code="DRAFT_SCHEMA_INVALID",
                    message=f"draft schema invalid: {type(e).__name__}: {e}",
                    evidence_required=False,
                    severity="block",
                )
            ]

        valid_ids = _valid_segment_ids(evidence)
        if not valid_ids:
            violations.append(
                TruthViolation(
                    code="NO_EVIDENCE_SEGMENTS",
                    message="evidence bundle contains zero segment ids",
                    evidence_required=True,
                    severity="block",
                )
            )
            return violations

        # Citation integrity: every cited segment_id must exist in evidence
        anchor_refs: Iterable[_AnchorRef]
        if mode_s == "meeting":
            anchor_refs = _iter_minutes_anchor_refs(payload)
        else:
            anchor_refs = _iter_journal_anchor_refs(payload)

        for ref in anchor_refs:
            if ref.segment_id is None:
                violations.append(
                    TruthViolation(
                        code="CITATION_MISSING_SEGMENT_ID",
                        message=f"citation missing segment_id at {ref.where}",
                        evidence_required=True,
                        severity="block",
                        meta={"where": ref.where},
                    )
                )
                continue

            if ref.segment_id not in valid_ids:
                violations.append(
                    TruthViolation(
                        code="CITATION_UNKNOWN_SEGMENT",
                        message=f"citation references unknown segment_id={ref.segment_id} at {ref.where}",
                        evidence_required=True,
                        severity="block",
                        meta={"segment_id": ref.segment_id, "where": ref.where},
                    )
                )

        # Identity grounding: only allow names when speaker overlay exists.
        overlay = _extract_overlay_mapping(evidence)
        diar_conf = _extract_diarization_confidence(evidence)

        if mode_s == "meeting":
            participants = payload.get("participants")
            if isinstance(participants, list):
                for idx, p in enumerate(participants):
                    if not isinstance(p, dict):
                        continue
                    dn = p.get("display_name")
                    if not isinstance(dn, str) or not dn.strip():
                        continue

                    # A display_name without an overlay is an ungrounded identity claim.
                    if not overlay:
                        violations.append(
                            TruthViolation(
                                code="DISPLAY_NAME_WITHOUT_OVERLAY",
                                message="participant display_name present but no speaker-map overlay evidence",
                                evidence_required=True,
                                severity="block",
                                meta={"participant_index": idx, "display_name": dn},
                            )
                        )
                        continue

                    spk = p.get("speaker_label")
                    spk_s = str(spk or "").strip().upper()
                    expected = overlay.get(spk_s)
                    if expected and expected != dn.strip():
                        violations.append(
                            TruthViolation(
                                code="DISPLAY_NAME_MISMATCH_OVERLAY",
                                message="participant display_name does not match overlay mapping",
                                evidence_required=True,
                                severity="block",
                                meta={"speaker_label": spk_s, "display_name": dn, "overlay": expected},
                            )
                        )

                    if diar_conf is not None and diar_conf < self.diarization_confidence_warn_threshold:
                        violations.append(
                            TruthViolation(
                                code="LOW_DIARIZATION_CONFIDENCE_IDENTITY",
                                message="diarization confidence is low; speaker identity claims should be treated as uncertain",
                                evidence_required=False,
                                severity="warn",
                                meta={"confidence": diar_conf},
                            )
                        )

        # Assignee grounding (meeting + journal)
        allowed_names = {v for v in overlay.values()} if overlay else set()

        def check_assignees(items: Any, *, where: str) -> None:
            if not isinstance(items, list):
                return
            for it in items:
                if not isinstance(it, dict):
                    continue
                assignee = it.get("assignee")
                if assignee is None:
                    continue
                if not isinstance(assignee, str) or not assignee.strip():
                    continue

                a = assignee.strip()
                if _SPEAKER_LABEL_RE.match(a):
                    continue

                # If user provided a speaker overlay, we allow exact overlay names.
                if allowed_names and a in allowed_names:
                    if diar_conf is not None and diar_conf < self.diarization_confidence_warn_threshold:
                        violations.append(
                            TruthViolation(
                                code="LOW_DIARIZATION_CONFIDENCE_ASSIGNEE",
                                message="diarization confidence is low; named assignees may be uncertain",
                                evidence_required=False,
                                severity="warn",
                                meta={"confidence": diar_conf, "assignee": a},
                            )
                        )
                    continue

                violations.append(
                    TruthViolation(
                        code="ASSIGNEE_NOT_GROUNDED",
                        message=f"assignee '{a}' is not a speaker label and is not backed by overlay mapping",
                        evidence_required=True,
                        severity="block",
                        meta={"where": where, "assignee": a},
                    )
                )

        if mode_s == "meeting":
            check_assignees(payload.get("action_items"), where="minutes.action_items")
        else:
            check_assignees(payload.get("action_items"), where="journal.action_items")

        return violations

    def rewrite(self, draft: str, evidence: EvidenceBundle, violations: List[TruthViolation]) -> Optional[str]:
        # We intentionally do not auto-rewrite meeting artifacts yet.
        # If blocked, the pipeline should stop and force a human-visible fix.
        return None
