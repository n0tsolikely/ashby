#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _tail_lines(path: Path, lines: int) -> List[str]:
    if not path.exists() or lines <= 0:
        return []
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return data[-lines:]


def _tail_jsonl(path: Path, lines: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for ln in _tail_lines(path, lines):
        s = ln.strip()
        if not s:
            continue
        try:
            row = json.loads(s)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _cause_category(alert: Dict[str, Any]) -> str:
    event = str(alert.get("event") or "")
    if event == "alert.llm_disabled_on_chat":
        return "provider_disabled"
    if event == "alert.llm_error":
        return "llm_error"
    if event == "alert.audio_missing":
        return "missing_file"
    if event == "alert.ui_fetch_failed":
        return "fetch_failed"
    if event == "alert.ui_error":
        return "ui_error"
    if event == "alert.pipeline_degraded":
        return "pipeline_degraded"
    if event == "alert.backend_exception":
        return "backend_exception"
    return "unknown"


def run_doctor(stuart_root: Path, lines: int) -> str:
    rt = stuart_root / "realtime_log"
    events = _tail_jsonl(rt / "events.jsonl", lines)
    alerts = _tail_jsonl(rt / "alerts.jsonl", lines)

    if not alerts:
        return "No alerts found in realtime logs."

    events_by_cid: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in events:
        cid = str(row.get("correlation_id") or "")
        if not cid:
            continue
        events_by_cid[cid].append(row)

    out: List[str] = []
    out.append(f"alerts={len(alerts)} events={len(events)}")
    out.append("")

    for idx, alert in enumerate(alerts, start=1):
        cid = str(alert.get("correlation_id") or "")
        category = _cause_category(alert)
        out.append(f"[{idx}] correlation_id={cid or '<missing>'}")
        out.append(f"  alert_event={alert.get('event')} level={alert.get('level')} cause={category}")
        out.append(f"  summary={str(alert.get('summary') or '').strip()[:300]}")

        chain = sorted(events_by_cid.get(cid, []), key=lambda r: (int(r.get("seq") or 0), str(r.get("ts_utc") or "")))
        if not chain:
            out.append("  chain: <no matching events>")
        else:
            out.append("  chain:")
            for row in chain:
                ev = str(row.get("event") or "")
                comp = str(row.get("component") or "")
                seq = row.get("seq")
                summ = str(row.get("summary") or "").strip()[:180]
                out.append(f"    - seq={seq} component={comp} event={ev} summary={summ}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diagnose Stuart realtime observability chains from local JSONL logs")
    p.add_argument("--stuart-root", required=True, help="Stuart runtime root (contains realtime_log/) ")
    p.add_argument("--lines", type=int, default=400, help="How many trailing lines to inspect from each JSONL file")
    args = p.parse_args(argv)

    text = run_doctor(Path(args.stuart_root).expanduser().resolve(), int(args.lines))
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
