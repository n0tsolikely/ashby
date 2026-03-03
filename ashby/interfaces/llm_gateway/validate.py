from __future__ import annotations

import time
from typing import Any, Dict

from ashby.interfaces.llm_gateway.schemas import ChatGatewayRequest, ChatOutputV1, FormalizeRequest
from ashby.modules.meetings.schemas.journal_v1 import validate_journal_v1
from ashby.modules.meetings.schemas.minutes_v1 import validate_minutes_v1


def validate_formalization_request(request: FormalizeRequest) -> None:
    has_text = bool((request.transcript_text or "").strip())
    has_segments = bool(request.transcript_segments)
    if not has_text and not has_segments:
        raise ValueError("formalize request must include transcript_text or transcript_segments")

    if not request.transcript_segments:
        return

    seen_segment_ids: set[str] = set()
    for idx, seg in enumerate(request.transcript_segments):
        where = f"transcript_segments[{idx}]"
        if not seg.segment_id.strip():
            raise ValueError(f"{where}.segment_id must not be blank")
        if seg.segment_id in seen_segment_ids:
            raise ValueError(f"{where}.segment_id must be unique; duplicate={seg.segment_id!r}")
        seen_segment_ids.add(seg.segment_id)
        if seg.start_ms < 0:
            raise ValueError(f"{where}.start_ms must be >= 0")
        if seg.end_ms < 0:
            raise ValueError(f"{where}.end_ms must be >= 0")
        if seg.end_ms < seg.start_ms:
            raise ValueError(f"{where}.end_ms must be >= start_ms")
        if not seg.speaker_label.strip():
            raise ValueError(f"{where}.speaker_label must not be blank")
        if not seg.text.strip():
            raise ValueError(f"{where}.text must not be blank")


def normalize_output_json(*, request: FormalizeRequest, request_id: str, output_json: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce provider output into canonical Stuart schema envelope fields before validation."""
    payload: Dict[str, Any] = dict(output_json or {})
    payload["version"] = 1
    payload["session_id"] = str(payload.get("session_id") or f"gateway_session_{request_id}")
    payload["run_id"] = str(payload.get("run_id") or f"gateway_run_{request_id}")
    header = payload.get("header")
    if not isinstance(header, dict):
        header = {}
    payload["header"] = header
    header.setdefault("mode", request.mode)
    header.setdefault("retention", request.retention)
    header.setdefault("template_id", request.template_id)
    header.setdefault("created_ts", time.time())
    return payload


def _ensure_minutes_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("participants", [])
    payload.setdefault("topics", [])
    payload.setdefault("decisions", [])
    payload.setdefault("action_items", [])
    payload.setdefault("notes", [])
    payload.setdefault("open_questions", [])
    return payload


def _ensure_journal_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("narrative_sections", [{"section_id": "sec_001", "text": "No content returned."}])
    payload.setdefault("action_items", [])
    payload.setdefault("key_points", [])
    payload.setdefault("feelings", [])
    payload.setdefault("mood", "")
    return payload


def validate_formalization_output(*, request: FormalizeRequest, request_id: str, output_json: Dict[str, Any]) -> Dict[str, Any]:
    """Validate normalized provider output against mode schema; raises ValueError on invalid."""
    payload = normalize_output_json(request=request, request_id=request_id, output_json=output_json)
    if request.mode == "meeting":
        validate_minutes_v1(_ensure_minutes_defaults(payload))
        return payload
    validate_journal_v1(_ensure_journal_defaults(payload))
    return payload


def validate_chat_request(request: ChatGatewayRequest) -> None:
    if not (request.question or "").strip():
        raise ValueError("chat request.question must not be blank")
    if request.scope not in {"session", "global"}:
        raise ValueError("chat request.scope must be session|global")


def validate_chat_output(*, request_id: str, output_json: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(output_json or {})
    try:
        model = ChatOutputV1.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"chat output schema invalid: {exc}") from exc
    out = model.model_dump()
    out["request_id"] = request_id
    return out
