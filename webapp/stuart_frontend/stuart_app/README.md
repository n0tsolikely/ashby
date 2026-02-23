# Stuart Frontend

This is the canonical Stuart Vite + React frontend workspace.

## Prerequisites

1. Node.js 18+
2. npm 9+

## Local development

1. Install dependencies:

```bash
npm install
```

2. Start dev server:

```bash
npm run dev
```

3. Open:

```text
http://127.0.0.1:4173/
```

## API wiring

- Default API base: relative `/api`
- Dev proxy target: `http://127.0.0.1:8000` (configured in `vite.config.js`)
- Optional override: `VITE_STUART_API_BASE`

## Build

```bash
npm run build
npm run preview
```
