from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

from ashby.modules.meetings.schemas.search import CitationAnchor


def _require_dict(payload: Any, *, name: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object")
    return payload


def _reject_unknown(payload: Dict[str, Any], *, allowed: set[str], name: str) -> None:
    unknown = sorted(set(payload.keys()) - allowed)
    if unknown:
        raise ValueError(f"{name} has unknown fields: {','.join(unknown)}")


def _require_str(payload: Dict[str, Any], key: str, *, name: str) -> str:
    val = payload.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"{name}.{key} must be a non-empty string")
    return val.strip()


def _optional_str(payload: Dict[str, Any], key: str) -> Optional[str]:
    val = payload.get(key)
    if val is None:
        return None
    if not isinstance(val, str):
        raise ValueError(f"{key} must be a string when provided")
    v = val.strip()
    return v or None


@dataclass(frozen=True)
class ChatActionOpenSessionV1:
    kind: Literal["open_session"]
    session_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": "open_session", "session_id": self.session_id}


@dataclass(frozen=True)
class ChatActionJumpToSegmentV1:
    kind: Literal["jump_to_segment"]
    session_id: str
    transcript_version_id: str
    segment_id: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "jump_to_segment",
            "session_id": self.session_id,
            "transcript_version_id": self.transcript_version_id,
            "segment_id": int(self.segment_id),
        }


@dataclass(frozen=True)
class ChatActionTemplateDraftV1:
    kind: Literal["template_draft"]
    mode: str
    template_title: str
    template_text: str
    defaults: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "template_draft",
            "mode": self.mode,
            "template_title": self.template_title,
            "template_text": self.template_text,
            "defaults": dict(self.defaults),
        }


ChatActionV1 = Union[ChatActionOpenSessionV1, ChatActionJumpToSegmentV1, ChatActionTemplateDraftV1]


def parse_chat_action_v1(payload: Any) -> ChatActionV1:
    data = _require_dict(payload, name="ChatActionV1")
    kind = _require_str(data, "kind", name="ChatActionV1")
    if kind == "open_session":
        _reject_unknown(data, allowed={"kind", "session_id"}, name="ChatActionV1")
        return ChatActionOpenSessionV1(kind="open_session", session_id=_require_str(data, "session_id", name="ChatActionV1"))
    if kind == "jump_to_segment":
        _reject_unknown(
            data,
            allowed={"kind", "session_id", "transcript_version_id", "segment_id"},
            name="ChatActionV1",
        )
        seg = data.get("segment_id")
        if not isinstance(seg, int) or seg < 0:
            raise ValueError("ChatActionV1.segment_id must be an int >= 0")
        return ChatActionJumpToSegmentV1(
            kind="jump_to_segment",
            session_id=_require_str(data, "session_id", name="ChatActionV1"),
            transcript_version_id=_require_str(data, "transcript_version_id", name="ChatActionV1"),
            segment_id=seg,
        )
    if kind == "template_draft":
        _reject_unknown(
            data,
            allowed={"kind", "mode", "template_title", "template_text", "defaults"},
            name="ChatActionV1",
        )
        defaults = data.get("defaults")
        if defaults is None:
            defaults = {}
        if not isinstance(defaults, dict):
            raise ValueError("ChatActionV1.defaults must be an object when provided")
        return ChatActionTemplateDraftV1(
            kind="template_draft",
            mode=_require_str(data, "mode", name="ChatActionV1"),
            template_title=_require_str(data, "template_title", name="ChatActionV1"),
            template_text=_require_str(data, "template_text", name="ChatActionV1"),
            defaults={
                "include_citations": bool(defaults.get("include_citations", False)),
                "show_empty_sections": bool(defaults.get("show_empty_sections", False)),
            },
        )
    raise ValueError("ChatActionV1.kind must be one of: open_session,jump_to_segment,template_draft")


@dataclass(frozen=True)
class ChatHitV1:
    session_id: str
    run_id: str
    snippet: str
    score: float
    citation: CitationAnchor
    match_kind: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "snippet": self.snippet,
            "score": float(self.score),
            "match_kind": self.match_kind,
            "citation": self.citation.to_dict(),
        }


def parse_chat_hit_v1(payload: Any) -> ChatHitV1:
    data = _require_dict(payload, name="ChatHitV1")
    _reject_unknown(
        data,
        allowed={"session_id", "run_id", "snippet", "score", "citation", "match_kind"},
        name="ChatHitV1",
    )
    citation_raw = _require_dict(data.get("citation"), name="ChatHitV1.citation")
    citation = CitationAnchor(
        session_id=_require_str(citation_raw, "session_id", name="ChatHitV1.citation"),
        run_id=_require_str(citation_raw, "run_id", name="ChatHitV1.citation"),
        segment_id=int(citation_raw.get("segment_id")),
        speaker_label=_optional_str(citation_raw, "speaker_label"),
        t_start=(float(citation_raw["t_start"]) if isinstance(citation_raw.get("t_start"), (int, float)) else None),
        t_end=(float(citation_raw["t_end"]) if isinstance(citation_raw.get("t_end"), (int, float)) else None),
        source_path=_optional_str(citation_raw, "source_path"),
    )
    return ChatHitV1(
        session_id=_require_str(data, "session_id", name="ChatHitV1"),
        run_id=_require_str(data, "run_id", name="ChatHitV1"),
        snippet=_require_str(data, "snippet", name="ChatHitV1"),
        score=float(data.get("score") if isinstance(data.get("score"), (int, float)) else 0.0),
        citation=citation,
        match_kind=_optional_str(data, "match_kind"),
    )


@dataclass(frozen=True)
class ChatReplyV1:
    kind: Literal["assistant", "clarify", "planner"]
    text: str
    citations: List[CitationAnchor] = field(default_factory=list)
    hits: List[ChatHitV1] = field(default_factory=list)
    actions: List[ChatActionV1] = field(default_factory=list)
    clarify: Optional[Dict[str, Any]] = None
    planner: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "citations": [c.to_dict() for c in self.citations],
            "hits": [h.to_dict() for h in self.hits],
            "actions": [a.to_dict() for a in self.actions],
            "clarify": self.clarify,
            "planner": self.planner,
        }


def parse_chat_reply_v1(payload: Any) -> ChatReplyV1:
    data = _require_dict(payload, name="ChatReplyV1")
    _reject_unknown(
        data,
        allowed={"kind", "text", "citations", "hits", "actions", "clarify", "planner"},
        name="ChatReplyV1",
    )
    kind = _require_str(data, "kind", name="ChatReplyV1")
    if kind not in {"assistant", "clarify", "planner"}:
        raise ValueError("ChatReplyV1.kind must be assistant|clarify|planner")

    citations: List[CitationAnchor] = []
    for row in data.get("citations") or []:
        row_d = _require_dict(row, name="ChatReplyV1.citations[]")
        citations.append(
            CitationAnchor(
                session_id=_require_str(row_d, "session_id", name="ChatReplyV1.citations[]"),
                run_id=_require_str(row_d, "run_id", name="ChatReplyV1.citations[]"),
                segment_id=int(row_d.get("segment_id")),
                speaker_label=_optional_str(row_d, "speaker_label"),
                t_start=(float(row_d["t_start"]) if isinstance(row_d.get("t_start"), (int, float)) else None),
                t_end=(float(row_d["t_end"]) if isinstance(row_d.get("t_end"), (int, float)) else None),
                source_path=_optional_str(row_d, "source_path"),
            )
        )

    hits = [parse_chat_hit_v1(row) for row in (data.get("hits") or [])]
    actions = [parse_chat_action_v1(row) for row in (data.get("actions") or [])]
    text = _require_str(data, "text", name="ChatReplyV1")

    if kind == "clarify" and not isinstance(data.get("clarify"), dict):
        raise ValueError("ChatReplyV1.clarify must be present when kind=clarify")
    if kind == "planner" and not isinstance(data.get("planner"), dict):
        raise ValueError("ChatReplyV1.planner must be present when kind=planner")

    return ChatReplyV1(
        kind=kind,
        text=text,
        citations=citations,
        hits=hits,
        actions=actions,
        clarify=(dict(data.get("clarify")) if isinstance(data.get("clarify"), dict) else None),
        planner=(dict(data.get("planner")) if isinstance(data.get("planner"), dict) else None),
    )


@dataclass(frozen=True)
class ChatRequestV1:
    text: str
    session_id: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    history_tail: List[Dict[str, Any]] = field(default_factory=list)
    ui: Dict[str, Any] = field(default_factory=dict)
    client: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "text": self.text,
            "attachments": list(self.attachments),
            "history_tail": list(self.history_tail),
            "ui": dict(self.ui),
            "client": dict(self.client),
        }


def parse_chat_request_v1(payload: Any) -> ChatRequestV1:
    data = _require_dict(payload, name="ChatRequestV1")
    _reject_unknown(
        data,
        allowed={"session_id", "text", "attachments", "history_tail", "ui", "client"},
        name="ChatRequestV1",
    )
    text = _require_str(data, "text", name="ChatRequestV1")
    session_id = _optional_str(data, "session_id")
    attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
    history_tail = data.get("history_tail") if isinstance(data.get("history_tail"), list) else []
    ui = data.get("ui") if isinstance(data.get("ui"), dict) else {}
    client = data.get("client") if isinstance(data.get("client"), dict) else {}
    return ChatRequestV1(
        text=text,
        session_id=session_id,
        attachments=list(attachments),
        history_tail=list(history_tail),
        ui=dict(ui),
        client=dict(client),
    )


@dataclass(frozen=True)
class ChatResponseV1:
    reply: ChatReplyV1
    scope: Literal["session", "global"] = "session"
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "scope": self.scope,
            "reply": self.reply.to_dict(),
        }


def parse_chat_response_v1(payload: Any) -> ChatResponseV1:
    data = _require_dict(payload, name="ChatResponseV1")
    _reject_unknown(data, allowed={"session_id", "scope", "reply"}, name="ChatResponseV1")
    scope = str(data.get("scope") or "session").strip().lower()
    if scope not in {"session", "global"}:
        raise ValueError("ChatResponseV1.scope must be session|global")
    return ChatResponseV1(
        session_id=_optional_str(data, "session_id"),
        scope=scope,  # type: ignore[arg-type]
        reply=parse_chat_reply_v1(data.get("reply")),
    )
