# Stuart Frontend API Client

Client module: `stuart_app/src/api/stuartClient.js`

Base URL strategy:
- Default: relative `'/api'` (works with Vite proxy in local dev).
- Override: set `VITE_STUART_API_BASE` in environment, e.g. `http://127.0.0.1:8000/api`.

Implemented methods:
- `stuartClient.sessions.list()` -> `GET /api/sessions`
- `stuartClient.sessions.create(data)` -> `POST /api/sessions`
- `stuartClient.upload(file)` -> `POST /api/upload`
- `stuartClient.runs.create(data)` -> `POST /api/run`
- `stuartClient.runs.status(runId)` -> `GET /api/runs/{run_id}`
- `stuartClient.runs.listBySession(sessionId)` -> `GET /api/sessions/{session_id}/runs`
- `stuartClient.transcripts.list(sessionId)` -> `GET /api/sessions/{session_id}/transcripts`
- `stuartClient.transcripts.get(versionId)` -> `GET /api/transcripts/{transcript_version_id}`
- `stuartClient.formalizations.list(sessionId)` -> `GET /api/sessions/{session_id}/formalizations`
- `stuartClient.chat.session(data)` -> `POST /api/chat`
- `stuartClient.chat.global(data)` -> `POST /api/chat/global`
- `stuartClient.exportSession(sessionId, options)` -> `GET /api/sessions/{session_id}/export?...`

Error behavior:
- Non-2xx responses throw `Error` with backend message when available.
- UI call sites surface these errors via toast/banner; no simulated transcript/formalization/chat outputs are generated.
