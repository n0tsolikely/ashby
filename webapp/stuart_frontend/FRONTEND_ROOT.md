# Stuart Frontend Root Contract (Quest 080)

This directory is the canonical root for the new Stuart Vite+React frontend.

- Canonical frontend root: `Ashby_Engine/webapp/stuart_frontend`
- Quest anchor: `QUEST_080` (D1 1of10)
- Subject: Stuart (Ashby)

## Non-Negotiable Rules

- No Base44 platform dependencies are allowed.
- No Base44 compatibility shim/client is allowed.
- Frontend code must call canonical Stuart API names directly.
- Upload is not run (`upload != run`) in UI behavior and API calls.

## Development Run Contract

From this directory (once app files are ingested in Quest 081):

```bash
npm install
npm run dev
```

Alternative package managers are allowed if chosen by quest execution (`pnpm` or `yarn`),
but one canonical command set must be documented in this file if changed later.

## Dev API Routing Strategy

Preferred strategy (to avoid CORS issues in local development):

- Vite dev server proxy routes `'/api'` to backend web door host/port.
- Frontend uses relative API paths (e.g. `/api/sessions`).

Fallback strategy:

- Use `VITE_STUART_API_BASE` only when proxy is not available.
- Keep API naming canonical and Stuart-native.

## Canonical API Surface (Frontend-Native from Day 1)

- `GET /api/sessions`
- `POST /api/upload`
- `POST /api/run`
- `GET /api/runs/{run_id}`
- `GET /api/sessions/{id}/transcripts`
- `GET /api/sessions/{id}/formalizations`
- `POST /api/chat`
- `GET /api/sessions/{id}/export`

## Later FastAPI Integration (Not Implemented in Quest 080)

Current Python web door remains intact during migration.

Planned integration approach:

1. Build frontend assets from this root.
2. Emit static build output into a deterministic path for serving.
3. Mount/serve built assets from FastAPI web door static/template surfaces.
4. Keep existing web door behavior stable until build output is verified.

This quest intentionally does not modify runtime serving wiring.

## Preservation Guardrail

Quest 080 must not overwrite or delete:

- `Ashby_Engine/webapp/static/js/app.js`
- `Ashby_Engine/webapp/templates/index.html`
