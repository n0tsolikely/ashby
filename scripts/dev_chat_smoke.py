#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

import httpx


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local smoke test for Stuart chat endpoints")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base web API URL")
    p.add_argument("--scope", choices=["session", "global"], default="global")
    p.add_argument("--session-id", default="", help="Session id for session scope")
    p.add_argument("--question", required=True, help="Question text")
    return p.parse_args()


def _request_payload(args: argparse.Namespace) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "text": args.question,
        "ui": {"scope_toggle": args.scope},
        "history_tail": [],
    }
    if args.session_id:
        payload["session_id"] = args.session_id
    return payload


def main() -> int:
    args = _parse_args()
    endpoint = "/api/chat" if args.scope == "session" else "/api/chat/global"
    if args.scope == "session" and not args.session_id:
        print("--session-id is required for --scope session", file=sys.stderr)
        return 2

    with httpx.Client(timeout=20.0) as client:
        resp = client.post(f"{args.base_url.rstrip('/')}{endpoint}", json=_request_payload(args))
    print(f"HTTP {resp.status_code}")
    body = resp.json()
    print(json.dumps(body, indent=2, sort_keys=True))

    reply = body.get("reply") if isinstance(body, dict) else None
    if isinstance(reply, dict):
        print("\n--- Reply ---")
        print(reply.get("text") or "")
        print("\n--- Citations ---")
        print(json.dumps(reply.get("citations") or [], indent=2, sort_keys=True))
        print("\n--- Actions ---")
        print(json.dumps(reply.get("actions") or [], indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
