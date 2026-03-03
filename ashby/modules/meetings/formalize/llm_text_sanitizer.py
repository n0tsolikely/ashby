from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Tuple


def _extract_readable_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_extract_readable_text(v) for v in value]
        joined = " ".join(p for p in parts if p)
        return " ".join(joined.split())
    if isinstance(value, dict):
        preferred = ("text", "summary", "title", "message", "content", "note", "narrative", "value")
        for k in preferred:
            if k in value:
                got = _extract_readable_text(value.get(k))
                if got:
                    return got
        parts = [_extract_readable_text(v) for v in value.values()]
        joined = " ".join(p for p in parts if p)
        return " ".join(joined.split())
    return ""


def _sanitize_text(value: Any, *, field_path: str) -> Any:
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw:
        return value
    if not (raw.startswith("{") or raw.startswith("[")):
        return value

    try:
        parsed = json.loads(raw)
    except Exception:
        return value

    cleaned = _extract_readable_text(parsed).strip()
    if not cleaned:
        raise ValueError(f"JSON-like text field sanitized to empty text at {field_path}")
    return cleaned


def _iter_paths(mode: str) -> Iterable[Tuple[str, str]]:
    if mode == "meeting":
        return (
            ("topics", "title"),
            ("topics", "summary"),
            ("decisions", "text"),
            ("action_items", "text"),
            ("notes", "text"),
            ("open_questions", "text"),
        )
    if mode == "journal":
        return (
            ("narrative_sections", "title"),
            ("narrative_sections", "text"),
            ("key_points", "text"),
            ("action_items", "text"),
            ("feelings", "text"),
        )
    return ()


def sanitize_llm_text_fields(payload: Dict[str, Any], *, mode: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("LLM payload must be an object")

    out = dict(payload)
    for list_key, field_key in _iter_paths(mode):
        rows = out.get(list_key)
        if not isinstance(rows, list):
            continue
        cleaned_rows: List[Any] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                cleaned_rows.append(row)
                continue
            row_copy = dict(row)
            if field_key in row_copy:
                row_copy[field_key] = _sanitize_text(row_copy.get(field_key), field_path=f"{list_key}[{idx}].{field_key}")
            cleaned_rows.append(row_copy)
        out[list_key] = cleaned_rows

    if mode == "journal" and "mood" in out:
        out["mood"] = _sanitize_text(out.get("mood"), field_path="mood")

    return out
