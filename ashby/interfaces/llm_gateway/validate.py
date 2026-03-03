from __future__ import annotations

import time
from typing import Any, Dict

from ashby.interfaces.llm_gateway.schemas import FormalizeRequest
from ashby.modules.meetings.schemas.journal_v1 import validate_journal_v1
from ashby.modules.meetings.schemas.minutes_v1 import validate_minutes_v1


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
