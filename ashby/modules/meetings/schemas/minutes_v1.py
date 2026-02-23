from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from ashby.modules.meetings.schemas.artifacts_v1 import require_keys


# ----------------------------
# minutes.json — v1 machine contract
# ----------------------------

class CitationAnchorV1(TypedDict, total=False):
    # Required
    segment_id: int
    # Optional (helpful for UIs/renderers; derived from transcript if available)
    t_start: float
    t_end: float
    speaker_label: str


class MinutesHeaderV1(TypedDict, total=False):
    # Human-facing
    title: str
    datetime: str  # ISO-8601 if known (user-supplied or inferred); optional

    # Provenance
    mode: str  # must be "meeting" for minutes
    retention: str  # LOW|MED|HIGH|NEAR_VERBATIM
    template_id: str
    created_ts: float  # unix seconds


class MinutesParticipantV1(TypedDict, total=False):
    speaker_label: str  # SPEAKER_00, etc.
    display_name: str  # optional mapping


class MinutesTopicV1(TypedDict, total=False):
    topic_id: str
    title: str
    summary: str
    citations: List[CitationAnchorV1]


class MinutesDecisionV1(TypedDict, total=False):
    decision_id: str
    text: str
    citations: List[CitationAnchorV1]


class MinutesActionItemV1(TypedDict, total=False):
    action_id: str
    text: str
    assignee: Optional[str]
    due_date: Optional[str]
    citations: List[CitationAnchorV1]


class MinutesNoteV1(TypedDict, total=False):
    note_id: str
    text: str
    citations: List[CitationAnchorV1]


class MinutesOpenQuestionV1(TypedDict, total=False):
    question_id: str
    text: str
    citations: List[CitationAnchorV1]


class MinutesV1(TypedDict):
    version: int
    session_id: str
    run_id: str
    header: MinutesHeaderV1
    participants: List[MinutesParticipantV1]
    topics: List[MinutesTopicV1]
    decisions: List[MinutesDecisionV1]
    action_items: List[MinutesActionItemV1]
    notes: List[MinutesNoteV1]
    open_questions: List[MinutesOpenQuestionV1]


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


def _validate_citations(obj: Dict[str, Any], *, key: str = "citations") -> None:
    if key not in obj:
        raise ValueError(f"missing required key: {key}")
    citations = obj.get(key)
    if not isinstance(citations, list):
        raise ValueError(f"{key} must be a list")
    if len(citations) == 0:
        raise ValueError(f"{key} must be non-empty")
    for a in citations:
        _validate_anchor(a)


def validate_minutes_v1(payload: Dict[str, Any]) -> None:
    """Validate minutes.json v1.

    Requirements:
    - version == 1
    - required top-level keys exist
    - list fields are lists
    - topic/decision/action/note/open_question items include non-empty citations
      with segment_id anchors (truth backbone)
    """
    require_keys(
        payload,
        [
            "version",
            "session_id",
            "run_id",
            "header",
            "participants",
            "topics",
            "decisions",
            "action_items",
            "notes",
            "open_questions",
        ],
    )
    if int(payload["version"]) != 1:
        raise ValueError("MinutesV1 version must be 1")

    if not isinstance(payload.get("header"), dict):
        raise ValueError("header must be an object")

    _require_list(payload, "participants")

    for t in _require_list(payload, "topics"):
        if not isinstance(t, dict):
            raise ValueError("topic must be an object")
        require_keys(t, ["topic_id", "title", "citations"])
        _validate_citations(t)

    for d in _require_list(payload, "decisions"):
        if not isinstance(d, dict):
            raise ValueError("decision must be an object")
        require_keys(d, ["decision_id", "text", "citations"])
        _validate_citations(d)

    for a in _require_list(payload, "action_items"):
        if not isinstance(a, dict):
            raise ValueError("action item must be an object")
        require_keys(a, ["action_id", "text", "citations"])
        _validate_citations(a)

    for n in _require_list(payload, "notes"):
        if not isinstance(n, dict):
            raise ValueError("note must be an object")
        require_keys(n, ["note_id", "text", "citations"])
        _validate_citations(n)

    for q in _require_list(payload, "open_questions"):
        if not isinstance(q, dict):
            raise ValueError("open question must be an object")
        require_keys(q, ["question_id", "text", "citations"])
        _validate_citations(q)
