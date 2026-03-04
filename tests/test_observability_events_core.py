from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.observability import events as ob


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        rows.append(json.loads(ln))
    return rows


def test_emit_disabled_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ASHBY_EVENT_LOGGING", raising=False)
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "rt"))
    ob.emit_event(
        level="INFO",
        source="backend",
        component="system",
        event="system.test",
        summary="test",
        correlation_id="cid-1",
        session_id=None,
        run_id=None,
        trace_id="cid-1",
        span_id="sp-1",
        parent_span_id=None,
        data={},
    )
    assert not (tmp_path / "rt" / "realtime_log").exists()


def test_emit_event_schema_fields_and_routing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "rt"))
    ob.emit_event(
        level="INFO",
        source="frontend",
        component="ui",
        event="ui.chat_send",
        summary="sent",
        correlation_id="cid-2",
        session_id="ses_1",
        run_id=None,
        trace_id="cid-2",
        span_id="sp-2",
        parent_span_id=None,
        data={"token": "secret123", "nested": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz"}},
    )
    rt = tmp_path / "rt" / "realtime_log"
    events_rows = _read_jsonl(rt / "events.jsonl")
    ui_rows = _read_jsonl(rt / "ui.jsonl")
    assert len(events_rows) == 1
    assert len(ui_rows) == 1
    row = events_rows[0]
    for key in (
        "schema_version",
        "ts_utc",
        "level",
        "source",
        "correlation_id",
        "session_id",
        "run_id",
        "trace_id",
        "span_id",
        "parent_span_id",
        "seq",
        "duration_ms",
        "component",
        "event",
        "summary",
        "data",
    ):
        assert key in row
    assert row["schema_version"] == "1.0"
    assert row["correlation_id"] == "cid-2"
    assert row["session_id"] == "ses_1"
    assert row["component"] == "ui"
    assert row["data"]["token"] == "[REDACTED]"
    assert row["data"]["nested"]["Authorization"] == "[REDACTED]"


def test_seq_monotonic_per_correlation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "rt"))
    ob.emit_event(
        level="INFO",
        source="backend",
        component="system",
        event="a",
        summary="a",
        correlation_id="cid-3",
        session_id=None,
        run_id=None,
        trace_id="cid-3",
        span_id="sp-1",
        parent_span_id=None,
        data={},
    )
    ob.emit_event(
        level="INFO",
        source="backend",
        component="system",
        event="b",
        summary="b",
        correlation_id="cid-3",
        session_id=None,
        run_id=None,
        trace_id="cid-3",
        span_id="sp-2",
        parent_span_id=None,
        data={},
    )
    rows = _read_jsonl(tmp_path / "rt" / "realtime_log" / "events.jsonl")
    seqs = [r["seq"] for r in rows if r["correlation_id"] == "cid-3"]
    assert seqs == sorted(seqs)
    assert seqs[0] + 1 == seqs[1]


def test_emit_alert_writes_alerts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "rt"))
    ob.emit_alert(
        level="ERROR",
        source="backend",
        component="api",
        event="alert.backend_exception",
        summary="boom",
        correlation_id="cid-4",
        session_id=None,
        run_id=None,
        trace_id="cid-4",
        span_id="sp-4",
        parent_span_id=None,
        data={"message": "Bearer xxxxxxxx"},
    )
    rt = tmp_path / "rt" / "realtime_log"
    assert len(_read_jsonl(rt / "events.jsonl")) >= 1
    alerts = _read_jsonl(rt / "alerts.jsonl")
    assert len(alerts) >= 1
    assert any(r.get("event") == "alert.backend_exception" for r in alerts)
    assert any(r.get("level") == "ERROR" for r in alerts)


def test_rotation_with_small_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "rt"))
    monkeypatch.setenv("ASHBY_EVENT_LOG_MAX_BYTES", "400")
    for i in range(20):
        ob.emit_event(
            level="INFO",
            source="backend",
            component="system",
            event=f"e{i}",
            summary=("x" * 80),
            correlation_id=f"cid-rot-{i}",
            session_id=None,
            run_id=None,
            trace_id=f"cid-rot-{i}",
            span_id=f"sp-{i}",
            parent_span_id=None,
            data={"i": i},
        )
    rt = tmp_path / "rt" / "realtime_log"
    assert (rt / "events.jsonl").exists()
    rotated = sorted(rt.glob("events_*.jsonl"))
    assert rotated
