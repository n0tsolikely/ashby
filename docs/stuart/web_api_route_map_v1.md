# Stuart Web API Route Map v1 (Dungeon 2)

## Ownership
- FastAPI assembly: `ashby/interfaces/web/app.py`
- Session read/write overlays: `ashby/interfaces/web/sessions.py`
- Run artifact/download helpers: `ashby/interfaces/web/runs.py`
- New shared envelope helpers: `ashby/interfaces/web/http_envelope.py`
- New API models: `ashby/interfaces/web/api_models_v1.py`
- New transcript service/routes: `ashby/interfaces/web/transcripts.py`
- New formalizations service/routes: `ashby/interfaces/web/formalizations.py`
- New export routes: `ashby/interfaces/web/export_api.py`
- New chat routes: `ashby/interfaces/web/chat_api.py`

## Route Map

| Endpoint | Target module/function | Backing truth |
|---|---|---|
| `GET /api/registry` | `registry_api.py` | static registry payload |
| `POST /api/sessions` | `sessions.py:create_session` | `sessions/<id>/session.json` |
| `GET /api/sessions` | `sessions.py:list_sessions` (+ derived metadata) | session manifests + run manifests/index |
| `GET /api/sessions/{id}` | `sessions.py:get_session_detail` | session manifest + state overlay + runs/contributions |
| `PATCH /api/sessions/{id}` | `sessions.py:patch_session_meta` | mutable overlay only (not `session.json`) |
| `DELETE /api/sessions/{id}` | `app.py:api_delete_session` | session/runs/contrib/overlay directories |
| `POST /api/upload` | `uploads.py:store_upload*` | contributions manifests + source files |
| `POST /api/run` | `store.create_run` + `run_job` | `runs/<id>/run.json` lifecycle |
| `GET /api/runs/{run_id}` | `store.get_run_state` + `runs.py` helpers | run manifest + artifacts |
| `GET /api/sessions/{id}/runs` | `app.py`/`runs.py` session run index | filtered run manifests |
| `GET /api/sessions/{id}/transcripts` | `transcripts.py:list_transcripts` | transcript/aligned transcript artifacts |
| `GET /api/transcripts/{tv_id}` | `transcripts.py:get_transcript` | transcript version materialized from run artifact |
| `GET /api/sessions/{id}/formalizations` | `formalizations.py:list_formalizations` | formalization artifacts + run plan params |
| `GET /api/sessions/{id}/export` | `export_api.py:create_or_get_export` | `modules/meetings/export/bundle.py` |
| `GET /api/exports/{filename}` | `export_api.py:download_export` | `STUART_ROOT/exports` only |
| `POST /api/chat` | `chat_api.py:chat_session` | planner/clarify response only |
| `POST /api/chat/global` | `chat_api.py:chat_global` | scaffold response (or not implemented) |
| `POST /api/message` | compatibility alias | same planner substrate as chat session |

## Compatibility Guardrails
- Keep legacy fields during migration if frontend already consumes them.
- Additive changes first; tighten after client migration.
- No endpoint may fabricate transcript/formalization artifacts.
