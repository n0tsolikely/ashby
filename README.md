# Ashby Engine

Ashby is a **local-first agentic platform** that turns intelligence into reliable operations by enforcing **truth, state, policy, and execution contracts** across removable modules and swappable adapters.

Ashby is not “an assistant that talks.” Ashby is an operating system for agency: interpret intent, constrain with policy, execute through controlled interfaces, verify outcomes, update durable state + artifacts, and speak only what evidence supports.

This repository is the **engine**: the code that runs pipelines, APIs, and the Stuart v1 web UI.

**Stuart** is a meetings module implemented in this engine; it turns audio/transcripts/sessions into durable outputs (JSON / Markdown / PDF) without “guessing” or silently fabricating content.

> If you’re looking for the **Codex + governance + operational state** (Guild Orders / Quests / Snapshots / Audits / Canonical Vision), that lives in the separate repo: **`Ashby_Data`**.

---

## Repos (separated on purpose)

- **Engine (this repo)**: runtime code  
  - root corresponds to the `Ashby_Engine/` folder in the Canon.
- **Governance / Canon / Operational state**: `Ashby_Data` repo  
  - root corresponds to the `Ashby_Data/` folder in the Canon.
  - includes:
    - `Docs/ASHBY_THE_CANONICAL_VISION_2026-01-13.txt`
    - `Docs/ASHBY_CANONICAL_TECHNICAL_BLUEPRINT_2026-01-13.txt`
    - `Codex/ASHBY CODEX FULL.txt`
    - Guild Orders / Quest Board / Snapshots / Audits / etc.

---

## What Ashby Is / Is Not (Canonical Vision summary)

Ashby is not:
- a wrapper around a large language model
- a chatbot with plugins
- a bundle of scripts glued together by vibes
- a monolithic god-file
- a vendor-controlled cloud service pretending to be local
- a system that guesses when uncertain

## What’s actually implemented here

### Stuart v1 (Ashby Meetings Module)
Stuart v1 is implemented as an Ashby module at:

- `ashby/modules/meetings/` (meeting/journal pipeline + artifacts)
- Web API assembly:
  - `ashby/interfaces/web/app.py`
- Frontend (Vite):
  - `webapp/stuart_frontend/stuart_app/`

Stuart writes runtime session artifacts under **`STUART_ROOT`** (outside the repo):
- default: `~/ashby_runtime/stuart`
- config: `ashby/modules/meetings/config.py`

### LLM Gateway (Gemini)
The engine includes a small HTTP gateway for LLM calls:

- FastAPI app: `ashby/interfaces/llm_gateway/app.py`
- Provider (Gemini): `ashby/interfaces/llm_gateway/providers/gemini.py`

Meeting formalization uses the gateway client:
- `ashby/modules/llm/http_gateway.py`
- default gateway URL: `http://127.0.0.1:8787` (`STUART_LLM_GATEWAY_URL` to override)

---

## Quickstart (Stuart stack)

### 0) System deps
You need at minimum:
- `python3`
- `npm`
- `ffmpeg`

Docs: `docs/stuart/SYSTEM_DEPENDENCIES.md`

### 1) Boot the full stack (backend + frontend)
From repo root:

```bash
./Stuart
```

What it does (see the `Stuart` bash script in repo root):
- creates `.venv/` if missing
- installs Python deps from `requirements-stuart-v1.txt`
- installs frontend deps (`npm install`)
- starts backend + frontend via `scripts/stuart_up.sh`

Defaults:
- backend: `http://127.0.0.1:8844` (`STUART_WEB_PORT`)
- frontend: `http://127.0.0.1:4173` (`STUART_FRONTEND_PORT`)

### 2) Run backend only
```bash
PYTHONPATH=. python3 scripts/stuart_web.py
```

### 3) Preflight checks
```bash
python3 scripts/stuart_preflight.py
# or strict:
python3 scripts/stuart_preflight.py --strict
```

Install/verify guide: `docs/stuart/INSTALL_STUART_V1.md`

---

## Running the Gemini LLM Gateway

Export your key:

```bash
export GEMINI_API_KEY="..."
# optional:
export GEMINI_MODEL="gemini-2.5-flash"
```

Start the gateway on the default port expected by the meeting formalizer:

```bash
PYTHONPATH=. uvicorn ashby.interfaces.llm_gateway.app:app --host 127.0.0.1 --port 8787
```

Notes:
- Gateway provider is selected by `LLM_GATEWAY_PROVIDER` (default: `gemini`)
- If `GEMINI_API_KEY` is missing, the gateway fails fast (by design)

---

## Execution profiles (network egress gating)

Ashby uses explicit execution profiles:

- `LOCAL_ONLY` (default): **no network egress allowed**
- `HYBRID`: network egress requires explicit consent record
- `CLOUD`: network egress allowed

Code: `ashby/core/profile.py`  
Env var: `ASHBY_EXECUTION_PROFILE`

---

## Tests and smoke

### Unit tests
```bash
PYTHONPATH=. pytest -q
```

### Web API smoke script
There’s a scripted smoke for the Stuart web API:

- `scripts/smoke_stuart_web_api_v1.sh`

---

## Docs worth reading (in this repo)

- Ashby Codex (developer mirror):
  - `docs/ashby_codex/ashby_codex_full.txt`
  - plus `docs/ashby_codex/sections/`
  - canonical Codex + governance artifacts live in `Ashby_Data`
- Stuart v1 docs:
  - `docs/stuart/INSTALL_STUART_V1.md`
  - `docs/stuart/SYSTEM_DEPENDENCIES.md`
  - `docs/stuart/web_api_contract_v1.md`
  - `docs/stuart/web_api_route_map_v1.md`
  - `docs/stuart/transcript_versioning_model_v1.md`

---

## Repo map (top-level)

- `ashby/` — core engine package (modules, interfaces, adapters)
- `webapp/` — FastAPI web door + Vite frontend
- `scripts/` — boot scripts + smoke scripts
- `docs/` — codex + Stuart docs
- `tests/` — test suite
- `secrets_store/` — **redacted placeholders** (real secrets should never be committed)
- `runtime/`, `memory/` — local state (gitignored by default)

---

## Non-goals (current)
- This repo is not the governance OS. Governance artifacts belong in `Ashby_Data`.
- No silent “magic” execution: explicit runs, explicit outputs, explicit receipts. (If something can’t be verified, it should say so.)

---

## License
TBD
