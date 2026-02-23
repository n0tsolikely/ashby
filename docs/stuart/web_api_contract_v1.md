# Stuart Web API Contract v1 (Dungeon 2)

## Global Rules
- Upload is not Run. `POST /api/upload` stores contribution only.
- Artifacts on disk are source of truth (JSON/MD/PDF). No fabricated transcript/formalization content.
- Chat is control/scaffold only in v1. Chat must not auto-trigger `POST /api/run`.
- List endpoints are deterministic: newest first by `created_ts`, tie-break by stable id.

## Error Envelope
- Success:
```json
{"ok": true, "trace": {"request_id": "..."}, "...": "..."}
```
- Failure:
```json
{"ok": false, "error": {"code": "NOT_FOUND", "message": "..."}, "trace": {"request_id": "..."}}
```
- Canonical codes: `INVALID_REQUEST`, `NOT_FOUND`, `NOT_IMPLEMENTED`, `INTERNAL_ERROR`.

## Transcript Version ID Strategy
- `transcript_version_id = "tv__" + run_id`.
- Reversible mapping:
  - `run_id = transcript_version_id.replace("tv__", "", 1)`
- Deterministic and stable for v1.

## export_type Semantics
- `full_bundle`: all allowed session manifests/receipts/run artifacts (excluding prior export zips recursion).
- `transcript_only`: transcript substrate + receipts/manifests; excludes formalization outputs.
- `formalization_only`: formalization outputs + evidence + receipts needed to verify output lineage.

## Endpoint Table

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/registry` | Capabilities metadata | Envelope-wrapped |
| `POST /api/sessions` | Create session | Requires mode |
| `GET /api/sessions` | Session list | `limit/offset/q/mode` |
| `GET /api/sessions/{session_id}` | Session detail | Includes counts and run/contribution summaries |
| `PATCH /api/sessions/{session_id}` | Mutable metadata overlay | `title` v1; does not mutate `session.json` |
| `DELETE /api/sessions/{session_id}` | Delete session subtree | Deterministic response |
| `POST /api/upload` | Store upload contribution | No processing side effect |
| `POST /api/run` | Create run | Explicit execution |
| `GET /api/runs/{run_id}` | Run status/progress/downloads | Canonical run detail |
| `GET /api/sessions/{session_id}/runs` | Runs list for session | Deterministic ordering |
| `GET /api/sessions/{session_id}/transcripts` | Transcript versions list | Uses transcript version IDs |
| `GET /api/transcripts/{transcript_version_id}` | Transcript version detail | Segment substrate JSON |
| `GET /api/sessions/{session_id}/formalizations` | Formalization index | Real outputs only |
| `GET /api/sessions/{session_id}/export` | Create/return export metadata | Supports `export_type` |
| `GET /api/exports/{filename}` | Download export zip | Strict filename validation |
| `POST /api/chat` | Session chat scaffold | No run side effects |
| `POST /api/chat/global` | Global chat scaffold | May return NOT_IMPLEMENTED in v1 |
| `POST /api/message` | Legacy alias | Deprecated; maps to chat/planner behavior |

## Minimal Response Shapes
- `GET /api/sessions`:
```json
{"ok": true, "sessions": [], "page": {"limit": 50, "offset": 0, "returned": 0}}
```
- `GET /api/sessions/{session_id}/transcripts`:
```json
{"ok": true, "session_id": "ses_...", "transcripts": [], "page": {"limit": 50, "offset": 0, "returned": 0}}
```
- `GET /api/transcripts/{transcript_version_id}`:
```json
{"ok": true, "transcript": {"transcript_version_id": "tv__run_...", "run_id": "run_...", "segments": []}}
```
- `GET /api/sessions/{session_id}/export?export_type=full_bundle`:
```json
{"ok": true, "session_id": "ses_...", "export_type": "full_bundle", "zip": {"name": "....zip", "download_url": "/api/exports/....zip"}}
```

## Curl Examples
```bash
curl -s http://127.0.0.1:8844/api/sessions
curl -s -X POST http://127.0.0.1:8844/api/sessions -H 'Content-Type: application/json' -d '{"mode":"meeting","title":"Session A"}'
curl -s http://127.0.0.1:8844/api/sessions/ses_xxx/runs
curl -s http://127.0.0.1:8844/api/sessions/ses_xxx/transcripts
curl -s http://127.0.0.1:8844/api/transcripts/tv__run_xxx
curl -s "http://127.0.0.1:8844/api/sessions/ses_xxx/export?export_type=full_bundle"
curl -s -X POST http://127.0.0.1:8844/api/chat -H 'Content-Type: application/json' -d '{"session_id":"ses_xxx","text":"help"}'
```
