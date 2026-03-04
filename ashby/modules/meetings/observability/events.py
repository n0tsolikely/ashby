from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.config import get_config

SCHEMA_VERSION = "1.0"
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
_SEQ_BY_CORRELATION: Dict[str, int] = {}
_LOCK = threading.Lock()

_ALERT_EVENT_MAP = {
    "alert.backend_exception",
    "alert.ui_error",
    "alert.ui_fetch_failed",
    "alert.audio_missing",
    "alert.llm_not_called",
    "alert.llm_disabled_on_chat",
    "alert.llm_error",
    "alert.pipeline_degraded",
}

_SECRET_KEY_RE = re.compile(
    r"(authorization|token|secret|password|client_secret|refresh_token|api[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE_RE = re.compile(
    r"(bearer\s+[A-Za-z0-9\-\._~\+/=]+|sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z\-_]{16,}|ya29\.[0-9A-Za-z\-_]+)",
    re.IGNORECASE,
)
_LONG_BLOB_RE = re.compile(r"^[A-Za-z0-9+/=_-]{64,}$")


def is_enabled() -> bool:
    return (os.environ.get("ASHBY_EVENT_LOGGING") or "").strip() == "1"


def get_stuart_root() -> Path:
    return get_config().root


def ensure_realtime_dir(stuart_root: Path) -> Path:
    rt = Path(stuart_root) / "realtime_log"
    rt.mkdir(parents=True, exist_ok=True)
    return rt


def _max_bytes() -> int:
    raw = (os.environ.get("ASHBY_EVENT_LOG_MAX_BYTES") or "").strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except Exception:
            pass
    return DEFAULT_MAX_BYTES


def rotate_if_needed(path: Path) -> None:
    try:
        if not path.exists():
            return
        if path.stat().st_size <= _max_bytes():
            return
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        n = 1
        while True:
            candidate = parent / f"{stem}_{n}{suffix}"
            if not candidate.exists():
                path.rename(candidate)
                break
            n += 1
    except Exception:
        return


def next_seq(correlation_id: str) -> int:
    cid = str(correlation_id or "")
    with _LOCK:
        v = _SEQ_BY_CORRELATION.get(cid, 0)
        _SEQ_BY_CORRELATION[cid] = v + 1
        return v


def _redact_string(value: str) -> str:
    s = str(value)
    if _SECRET_VALUE_RE.search(s):
        return "[REDACTED]"
    if _LONG_BLOB_RE.match(s):
        return "[REDACTED_BLOB]"
    return s


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)
            if _SECRET_KEY_RE.search(key):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return _redact_string(obj)
    return obj


def write_jsonl(path: Path, event_obj: Dict[str, Any]) -> None:
    try:
        rotate_if_needed(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event_obj, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
    except Exception:
        return


def _build_event(
    *,
    level: str,
    source: str,
    component: str,
    event: str,
    summary: str,
    correlation_id: str,
    session_id: Optional[str],
    run_id: Optional[str],
    trace_id: str,
    span_id: str,
    parent_span_id: Optional[str],
    duration_ms: Optional[int],
    data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    lvl = str(level or "INFO").upper()
    cid = str(correlation_id or "").strip() or str(uuid.uuid4())
    trc = str(trace_id or "").strip() or cid
    spn = str(span_id or "").strip() or str(uuid.uuid4())
    payload = redact(data or {})
    return {
        "schema_version": SCHEMA_VERSION,
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": lvl,
        "source": str(source or "backend"),
        "correlation_id": cid,
        "session_id": (str(session_id) if session_id is not None else None),
        "run_id": (str(run_id) if run_id is not None else None),
        "trace_id": trc,
        "span_id": spn,
        "parent_span_id": (str(parent_span_id) if parent_span_id is not None else None),
        "seq": next_seq(cid),
        "duration_ms": (int(duration_ms) if duration_ms is not None else None),
        "component": str(component or "system"),
        "event": str(event or ""),
        "summary": _redact_string(str(summary or "")),
        "data": payload,
    }


def emit_event(
    *,
    level: str,
    source: str,
    component: str,
    event: str,
    summary: str,
    correlation_id: str,
    session_id: Optional[str],
    run_id: Optional[str],
    trace_id: str,
    span_id: str,
    parent_span_id: Optional[str],
    duration_ms: Optional[int] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    if not is_enabled():
        return
    root = get_stuart_root()
    rt = ensure_realtime_dir(root)
    row = _build_event(
        level=level,
        source=source,
        component=component,
        event=event,
        summary=summary,
        correlation_id=correlation_id,
        session_id=session_id,
        run_id=run_id,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        duration_ms=duration_ms,
        data=data,
    )
    write_jsonl(rt / "events.jsonl", row)
    if str(component) == "ui":
        write_jsonl(rt / "ui.jsonl", row)
    if str(component) == "llm":
        write_jsonl(rt / "llm.jsonl", row)
    if str(row.get("level")) in {"WARNING", "ERROR"}:
        write_jsonl(rt / "alerts.jsonl", row)


def emit_alert(
    *,
    level: str,
    source: str,
    component: str,
    event: str,
    summary: str,
    correlation_id: str,
    session_id: Optional[str],
    run_id: Optional[str],
    trace_id: str,
    span_id: str,
    parent_span_id: Optional[str],
    duration_ms: Optional[int] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    lvl = str(level or "WARNING").upper()
    if lvl not in {"WARNING", "ERROR"}:
        lvl = "WARNING"
    emit_event(
        level=lvl,
        source=source,
        component=component,
        event=event,
        summary=summary,
        correlation_id=correlation_id,
        session_id=session_id,
        run_id=run_id,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        duration_ms=duration_ms,
        data=data,
    )
    if not is_enabled():
        return
    if event not in _ALERT_EVENT_MAP and lvl not in {"WARNING", "ERROR"}:
        return
    root = get_stuart_root()
    rt = ensure_realtime_dir(root)
    row = _build_event(
        level=lvl,
        source=source,
        component=component,
        event=event,
        summary=summary,
        correlation_id=correlation_id,
        session_id=session_id,
        run_id=run_id,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        duration_ms=duration_ms,
        data=data,
    )
    write_jsonl(rt / "alerts.jsonl", row)
