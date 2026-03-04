# Stuart Realtime Observability Logging

This is realtime debugging telemetry for Stuart.

When enabled, it records a causal chain across UI, API, pipeline, storage, and LLM seams using `correlation_id`.

## Enable

```bash
export ASHBY_EVENT_LOGGING=1
export STUART_ROOT="$HOME/ashby_runtime/stuart"
```

Telemetry files:

- `$STUART_ROOT/realtime_log/events.jsonl`
- `$STUART_ROOT/realtime_log/alerts.jsonl`
- `$STUART_ROOT/realtime_log/ui.jsonl`
- `$STUART_ROOT/realtime_log/llm.jsonl`

## Tail Logs

```bash
tail -f "$STUART_ROOT/realtime_log/events.jsonl"
tail -f "$STUART_ROOT/realtime_log/alerts.jsonl"
```

## Doctor Tool

```bash
cd /home/notsolikely/Ashby_Engine
python3 tools/realtime_log_doctor.py --stuart-root "$STUART_ROOT" --lines 400
```

Doctor behavior:

- reads recent alerts and events from local JSONL
- groups alerts by `correlation_id`
- prints causal chain events per alert
- prints likely cause categories (llm_error, fetch_failed, missing_file, etc.)

## Privacy And Safety

By design, telemetry does not log secrets or raw prompt/completion text.

- No API keys/tokens/passwords/auth headers
- No raw chat body or raw audio bytes in UI telemetry
- Chat UI telemetry stores only: `text_len`, `text_sha256`, `prefix_len=0`
- Upload UI telemetry stores only: filename and size
- Error strings are redacted/truncated before emit

## Operational Validation Pattern

1. Start Stuart with `ASHBY_EVENT_LOGGING=1` and runtime root outside repo.
2. Trigger UI actions (`run`, `upload`, `chat_send`, `export`).
3. Confirm events and alerts files populate.
4. Run doctor and verify grouped chains by `correlation_id`.
5. For degraded paths, confirm explicit alert events are present.
