# Stuart Runtime Audit Protocol

Purpose: enforce live observability checks while Stuart is being tested in the webapp.

## Required environment

```bash
export ASHBY_EVENT_LOGGING=1
export STUART_ROOT="${STUART_ROOT:-$HOME/ashby_runtime/stuart}"
```

## Start live audit watcher

```bash
# from Ashby_Engine repo root
bash tools/stuart_runtime_audit_watch.sh
```

This tails:
- `$STUART_ROOT/realtime_log/events.jsonl`
- `$STUART_ROOT/realtime_log/alerts.jsonl`
- `$STUART_ROOT/realtime_log/ui.jsonl`
- `$STUART_ROOT/realtime_log/llm.jsonl`

## Fast diagnosis for "chat is not using LLM"

Run:

```bash
tail -n 120 "$STUART_ROOT/realtime_log/llm.jsonl"
```

Interpretation:
- `llm.call` then `llm.response`: LLM path is active.
- `llm.error` + `alert.llm_error`: gateway/network/provider failure.
- `llm.fallback` without `llm.call`: fallback path used without invoking the gateway (for example, no evidence segments).
- `llm.fallback` after `llm.error`: LLM call failed and chat returned retrieval-only.

## Why this matters

This gives causal-chain auditing during your manual testing so we can answer:
- why a response came from fallback,
- why LLM was skipped,
- what correlation_id links UI action -> API route -> LLM decision.

## Current known behavior in this repo

Stuart chat currently runs with `selected_profile=HYBRID` from the UI, and the backend always attempts a gateway call when evidence is available.

Code paths:
- UI: `webapp/stuart_frontend/stuart_app/src/pages/Stuart.jsx` (builds `selected_profile`)
- Backend: `ashby/modules/meetings/chat/answer.py` (LLM call + fallback behavior)
