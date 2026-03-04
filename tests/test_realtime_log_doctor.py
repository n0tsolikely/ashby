from __future__ import annotations

import json
from pathlib import Path

from tools.realtime_log_doctor import run_doctor


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def test_realtime_log_doctor_groups_by_correlation_id(tmp_path: Path) -> None:
    rt = tmp_path / "realtime_log"
    _append_jsonl(
        rt / "events.jsonl",
        [
            {
                "schema_version": "1.0",
                "ts_utc": "2026-03-03T00:00:00Z",
                "level": "INFO",
                "source": "backend",
                "correlation_id": "cid_1",
                "session_id": "ses_1",
                "run_id": "run_1",
                "trace_id": "cid_1",
                "span_id": "s1",
                "parent_span_id": None,
                "seq": 0,
                "duration_ms": None,
                "component": "api",
                "event": "api.request_received",
                "summary": "req",
                "data": {},
            },
            {
                "schema_version": "1.0",
                "ts_utc": "2026-03-03T00:00:01Z",
                "level": "ERROR",
                "source": "backend",
                "correlation_id": "cid_1",
                "session_id": "ses_1",
                "run_id": "run_1",
                "trace_id": "cid_1",
                "span_id": "s2",
                "parent_span_id": "s1",
                "seq": 1,
                "duration_ms": 10,
                "component": "llm",
                "event": "llm.error",
                "summary": "llm failed",
                "data": {},
            },
        ],
    )
    _append_jsonl(
        rt / "alerts.jsonl",
        [
            {
                "schema_version": "1.0",
                "ts_utc": "2026-03-03T00:00:01Z",
                "level": "ERROR",
                "source": "backend",
                "correlation_id": "cid_1",
                "session_id": "ses_1",
                "run_id": "run_1",
                "trace_id": "cid_1",
                "span_id": "a1",
                "parent_span_id": "s1",
                "seq": 2,
                "duration_ms": 10,
                "component": "llm",
                "event": "alert.llm_error",
                "summary": "gateway failed",
                "data": {},
            }
        ],
    )

    text = run_doctor(tmp_path, 400)
    assert "correlation_id=cid_1" in text
    assert "cause=llm_error" in text
    assert "api.request_received" in text
    assert "llm.error" in text


def test_realtime_log_doctor_handles_empty(tmp_path: Path) -> None:
    assert run_doctor(tmp_path, 100).startswith("No alerts found")
