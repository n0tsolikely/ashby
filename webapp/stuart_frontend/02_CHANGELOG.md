# Stuart Frontend Change Log

## 2026-02-18

### Boot + Entrypoint Fixes
- Fixed module mismatch: `src/main.jsx` imports `@/App.jsx` while only `src/Apps.jsx` existed.
- Added canonical `src/App.jsx` and made `src/Apps.jsx` a compatibility re-export.
- Updated app boot to remove Base44 auth/nav wrappers from the render path.
- Updated `index.html` title/icon to Stuart-native values.

### Base44 Auth/Nav Wrapper Removal
- Removed Base44-dependent boot requirements by replacing auth/navigation glue with local no-op implementations:
  - `src/lib/AuthContext.jsx`
  - `src/lib/NavigationTracker.jsx`
  - `src/lib/app-params.js`
- Updated `src/lib/PageNotFound.jsx` to remove Base44 identity checks.

### Canonical API Wiring (No Base44 Shim)
- Added canonical Stuart API client: `src/api/stuartClient.js`.
- Refactored frontend call sites to canonical endpoints:
  - `src/components/stuart/AudioUploader.jsx` -> `/api/upload`
  - `src/pages/Stuart.jsx` -> `/api/sessions`, `/api/run`, `/api/sessions/{id}/formalizations`, `/api/chat`, `/api/sessions/{id}/export`
  - `src/pages/Sessions.jsx` -> `/api/sessions`
- Import strategy: retained `@/` alias across frontend source with aligned Vite `resolve.alias` and `jsconfig.json` `paths` mapping.

### Compile Outcome
- Before: App boot broke due to `@/App.jsx` import mismatch and missing Base44 client modules.
- After: Vite resolves entrypoint and app boot path without Base44 dependencies.
