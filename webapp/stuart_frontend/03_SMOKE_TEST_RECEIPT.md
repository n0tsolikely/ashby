# Stuart Frontend Smoke Test Receipt

Date: 2026-02-18
Frontend root: `/home/notsolikely/Ashby_Engine/webapp/stuart_frontend`
App workspace: `/home/notsolikely/Ashby_Engine/webapp/stuart_frontend/stuart_app`

## Commands run

```bash
npm install --no-audit --progress=false
npm run dev -- --host 127.0.0.1 --port 4173 --logLevel info
curl -sS http://127.0.0.1:4173/
npm run build
grep -R "<legacy_vendor_token>" /home/notsolikely/Ashby_Engine/webapp/stuart_frontend --exclude-dir=node_modules
grep -R "<legacy_llm_adapter_token>" /home/notsolikely/Ashby_Engine/webapp/stuart_frontend --exclude-dir=node_modules
```

## Results

- Install: success (`up to date in 1s`)
- Dev server: serving successfully at `http://127.0.0.1:4173/`
- URL fetch: index HTML served with Stuart title and root mount element
- Build: success (`npm run build` exit code 0)
- Grep purity: zero hits for legacy vendor/adaptor tokens (see audit receipt for exact command text)

## UI shell verification

- Router entry resolves (`/src/main.jsx` + canonical `src/App.jsx` path)
- Stuart shell components are mounted by `src/pages/Stuart.jsx`:
  - Header bar
  - Session list panel
  - Tabs (`Session`, `Chat`, `Outputs`)
- Backend-unavailable paths now fail with explicit UI error toasts (no simulated outputs)

## Notes

- This smoke confirms boot/serve/build and non-crash shell wiring.
- Transcript/formalization pipeline behavior remains dependent on backend endpoint availability.
