from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from ashby.modules.meetings.schemas.artifacts_v1 import require_keys


# ----------------------------
# evidence_map.json — v2 machine contract
# ----------------------------
# Purpose:
# - Provide claim-level anchors tying minutes/journal claims to transcript segments.
# - This is NOT external fact checking. It is traceability.


class EvidenceAnchorV2(TypedDict, total=False):
    # Required
    segment_id: int
    t_start: float
    t_end: float
    speaker_label: str


class EvidenceSourceV2(TypedDict, total=False):
    # Where the claim came from (minutes.json / journal.json)
    artifact: str  # "minutes.json" | "journal.json"
    item_type: str  # e.g. topic|decision|action_item|note|open_question|narrative|key_point|feeling
    item_id: str


class EvidenceClaimV2(TypedDict, total=False):
    # Required
    claim_id: str
    claim_type: str  # e.g. minutes.topic, minutes.decision, journal.narrative
    claim_text: str
    anchors: List[EvidenceAnchorV2]

    # Optional helpers
    title: str
    source: EvidenceSourceV2


class EvidenceMapV2(TypedDict):
    version: int
    session_id: str
    run_id: str
    mode: str  # meeting|journal
    claims: List[EvidenceClaimV2]


def _validate_anchor(a: Any) -> None:
    if not isinstance(a, dict):
        raise ValueError("evidence anchor must be an object")

    for k in ("segment_id", "t_start", "t_end", "speaker_label"):
        if k not in a:
            raise ValueError(f"evidence anchor missing required key: {k}")

    try:
        sid = int(a["segment_id"])
    except Exception:
        raise ValueError("evidence anchor segment_id must be int")
    if sid < 0:
        raise ValueError("evidence anchor segment_id must be >= 0")

    try:
        float(a["t_start"])
        float(a["t_end"])
    except Exception:
        raise ValueError("evidence anchor t_start/t_end must be float")

    if not isinstance(a.get("speaker_label"), str) or not a.get("speaker_label"):
        raise ValueError("evidence anchor speaker_label must be a non-empty string")


def _validate_claim(c: Any) -> None:
    if not isinstance(c, dict):
        raise ValueError("evidence claim must be an object")

    for k in ("claim_id", "claim_type", "claim_text", "anchors"):
        if k not in c:
            raise ValueError(f"evidence claim missing required key: {k}")

    if not isinstance(c.get("claim_id"), str) or not c.get("claim_id"):
        raise ValueError("evidence claim_id must be a non-empty string")

    if not isinstance(c.get("claim_type"), str) or not c.get("claim_type"):
        raise ValueError("evidence claim_type must be a non-empty string")

    if not isinstance(c.get("claim_text"), str):
        raise ValueError("evidence claim_text must be a string")

    anchors = c.get("anchors")
    if not isinstance(anchors, list):
        raise ValueError("evidence claim anchors must be a list")

    # anchors MAY be empty (e.g., optional-citation narrative sections), but if present must be valid.
    for a in anchors:
        _validate_anchor(a)


def validate_evidence_map_v2(payload: Dict[str, Any]) -> None:
    """Validate evidence_map.json v2.

    Requirements:
    - version == 2
    - required top-level keys exist
    - claims are claim-level objects with transcript anchors

    Note:
    - This validates traceability structure, not external truth.
    """

    require_keys(payload, ["version", "session_id", "run_id", "mode", "claims"])

    if int(payload["version"]) != 2:
        raise ValueError("EvidenceMapV2 version must be 2")

    if not isinstance(payload.get("session_id"), str):
        raise ValueError("EvidenceMapV2 session_id must be a string")

    if not isinstance(payload.get("run_id"), str):
        raise ValueError("EvidenceMapV2 run_id must be a string")

    if not isinstance(payload.get("mode"), str) or not payload.get("mode"):
        raise ValueError("EvidenceMapV2 mode must be a non-empty string")

    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("EvidenceMapV2 claims must be a list")

    for c in claims:
        _validate_claim(c)
