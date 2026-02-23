from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from ashby.modules.meetings.schemas.artifacts_v1 import require_keys


# ----------------------------
# journal.json — v1 machine contract
# ----------------------------

class CitationAnchorV1(TypedDict, total=False):
    # Required
    segment_id: int
    # Optional helpers (derived from transcript if available)
    t_start: float
    t_end: float
    speaker_label: str


class JournalHeaderV1(TypedDict, total=False):
    title: str
    datetime: str  # ISO-8601 if known (user-supplied or inferred); optional

    # Provenance
    mode: str  # must be "journal" for journaling mode
    retention: str  # LOW|MED|HIGH|NEAR_VERBATIM
    template_id: str
    created_ts: float  # unix seconds


class JournalNarrativeSectionV1(TypedDict, total=False):
    section_id: str
    title: str
    text: str

    # Optional:
    # - Narrative may be subjective and may omit citations.
    # - If citations are present, they must be non-empty anchors.
    citations: List[CitationAnchorV1]


class JournalKeyPointV1(TypedDict, total=False):
    point_id: str
    text: str
    citations: List[CitationAnchorV1]


class JournalFeelingV1(TypedDict, total=False):
    text: str
    citations: List[CitationAnchorV1]


class JournalActionItemV1(TypedDict, total=False):
    action_id: str
    text: str
    assignee: Optional[str]
    due_date: Optional[str]
    citations: List[CitationAnchorV1]


class JournalV1(TypedDict):
    version: int
    session_id: str
    run_id: str
    header: JournalHeaderV1
    narrative_sections: List[JournalNarrativeSectionV1]
    action_items: List[JournalActionItemV1]

    # Optional (template-driven)
    key_points: List[JournalKeyPointV1]
    mood: str
    feelings: List[JournalFeelingV1]


def _require_list(payload: Dict[str, Any], key: str) -> List[Any]:
    v = payload.get(key)
    if not isinstance(v, list):
        raise ValueError(f"{key} must be a list")
    return v


def _validate_anchor(anchor: Any) -> None:
    if not isinstance(anchor, dict):
        raise ValueError("citation anchor must be an object")
    if "segment_id" not in anchor:
        raise ValueError("citation anchor missing segment_id")
    try:
        sid = int(anchor["segment_id"])
    except Exception:
        raise ValueError("citation anchor segment_id must be int")
    if sid < 0:
        raise ValueError("citation anchor segment_id must be >= 0")


def _validate_optional_citations(obj: Dict[str, Any], *, key: str = "citations") -> None:
    if key not in obj:
        return
    citations = obj.get(key)
    if not isinstance(citations, list):
        raise ValueError(f"{key} must be a list")
    if len(citations) == 0:
        raise ValueError(f"{key} must be non-empty when present")
    for a in citations:
        _validate_anchor(a)


def _validate_required_citations(obj: Dict[str, Any], *, key: str = "citations") -> None:
    if key not in obj:
        raise ValueError(f"missing required key: {key}")
    citations = obj.get(key)
    if not isinstance(citations, list):
        raise ValueError(f"{key} must be a list")
    if len(citations) == 0:
        raise ValueError(f"{key} must be non-empty")
    for a in citations:
        _validate_anchor(a)


def validate_journal_v1(payload: Dict[str, Any]) -> None:
    """Validate journal.json v1.

    Requirements:
    - version == 1
    - required top-level keys exist
    - narrative_sections is a list of sections (citations optional)
    - key_points (if present) must include citations with segment_id anchors
    - action_items (if present) must include citations with segment_id anchors
    """
    require_keys(payload, ["version", "session_id", "run_id", "header", "narrative_sections", "action_items"])
    if int(payload["version"]) != 1:
        raise ValueError("JournalV1 version must be 1")

    if not isinstance(payload.get("header"), dict):
        raise ValueError("header must be an object")

    for s in _require_list(payload, "narrative_sections"):
        if not isinstance(s, dict):
            raise ValueError("narrative section must be an object")
        require_keys(s, ["section_id", "text"])
        _validate_optional_citations(s)

    if "key_points" in payload:
        for kp in _require_list(payload, "key_points"):
            if not isinstance(kp, dict):
                raise ValueError("key point must be an object")
            require_keys(kp, ["point_id", "text", "citations"])
            _validate_required_citations(kp)

    if "feelings" in payload:
        for f in _require_list(payload, "feelings"):
            if not isinstance(f, dict):
                raise ValueError("feeling must be an object")
            require_keys(f, ["text"])
            _validate_optional_citations(f)

    if "mood" in payload and not isinstance(payload.get("mood"), str):
        raise ValueError("mood must be a string")

    for a in _require_list(payload, "action_items"):
        if not isinstance(a, dict):
            raise ValueError("action item must be an object")
        require_keys(a, ["action_id", "text", "citations"])
        _validate_required_citations(a)
