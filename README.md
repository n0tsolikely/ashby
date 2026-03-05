# Ashby

Ashby is a **local-first AI home brain and modular agent platform**.

It allows a single conversational intelligence to control real-world systems, software services, and specialized AI modules while maintaining persistent state and evidence-based responses.

Ashby is designed to run **inside your home on your own hardware**, keeping your data private and under your control.

This repository is the **Ashby engine**: the runtime codebase. Today, the primary implemented module here is **Stuart** (meetings transcription + analysis).

> Canonical vision, Codex, governance, and operational state live in the separate repo: **`Ashby_Data`**.

---

## What Ashby Is

Ashby is a **brand-agnostic AI control layer for environments**.

Most smart home ecosystems today suffer from three major problems:

- Vendor lock-in
- Rigid command syntax
- Lack of persistent system state

Examples:

- Smart lights require brand-specific apps.
- Voice assistants require very specific phrasing.
- Most systems organize devices strictly by rooms.

Ashby introduces a different approach.
Instead of rigid commands, you interact with a system that understands natural language and the state of your environment.

Example:

```text
User:
"Ash, it's dark in here."

Ashby:
Turning on nearby lights.

User:
"These lights are burning my retinas."

Ashby:
Dimming lights.
```

---

## Why Ashby Exists

Modern smart homes are fragmented.

Typical setups involve:

- multiple apps
- incompatible ecosystems
- vendor lock-in
- cloud dependencies

Ashby attempts to unify everything under a **single intelligent system** that coordinates devices and AI modules through conversation.

---

## Local-First AI Home Brain

Ashby is designed to run locally.

This means:

- camera data can remain inside your home
- device state remains private
- automation does not depend on external cloud services

Ashby can still communicate externally when necessary, but the system itself is designed to function locally.

---

## Zones Instead of Rooms

Most smart home platforms organize devices strictly by rooms.

Humans do not think this way.
People think in zones.

Examples of zones:

- Downstairs
- Entertainment area
- Night mode
- Work area

Ashby introduces **Zones**, allowing:

- rooms to belong to multiple zones
- devices to belong to multiple zones
- zones to span arbitrary spaces

Example:

```text
Zone: Downstairs
  Living Room
  Kitchen
  Hallway

Zone: Night Mode
  Bedroom Lights
  Hallway Lights
```

This allows Ashby to reason about environments more naturally.

---

## Modular Architecture

Ashby is not a single AI.
It is a **platform for specialized AI modules**.

Each module performs a specific task.

Examples of modules include:

| Module | Purpose |
|------|------|
| Stuart | Meeting transcription and analysis |
| Camera Module | Computer vision for cameras |
| Inventory Module | Household inventory tracking |
| Energy Module | Energy monitoring |
| Environment Module | Lighting and climate control |

Ashby acts as the **central coordinator**.

Users talk to Ashby.
Ashby calls modules.
Modules return structured results.

---

## Architecture

```text
User
 |
 v
Ashby Core
 |
 +-- Stuart Module
 |
 +-- Camera Module
 |
 +-- Inventory Module
 |
 +-- Energy Module
 |
 +-- Device Adapters
      +-- Zigbee
      +-- Tuya
      +-- Home Assistant
      +-- Local APIs
```

Ashby coordinates modules and device adapters.
Modules provide specialized intelligence.
Adapters interact with hardware.

---

## Example Interaction

```text
User:
"Ash, I'm home."

Ashby:
"Welcome back. Turning on the living room lights."

User:
"Whoa those are bright."

Ashby:
"Sorry about that. Dimming them."

User:
"Way more."

Ashby:
"Dimming to 20%."
```

---

## Stuart (Meetings) Is The First Ashby Module

The first module being developed for Ashby is **Stuart**.

Stuart is an AI meeting assistant capable of:

- speaker diarization
- transcript generation
- meeting summaries
- structured decision extraction

Stuart is being built first because it is a **self-contained module that can ship independently** while the Ashby platform continues evolving.

### Where Stuart Lives (in this repo)

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

## Running the Stuart Module

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

### Running the Gemini LLM Gateway

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

### Execution profiles (network egress gating)

Ashby uses explicit execution profiles:

- `LOCAL_ONLY` (default): **no network egress allowed**
- `HYBRID`: network egress requires explicit consent record
- `CLOUD`: network egress allowed

Code: `ashby/core/profile.py`  
Env var: `ASHBY_EXECUTION_PROFILE`

---

### Tests and smoke

#### Unit tests
```bash
PYTHONPATH=. pytest -q
```

#### Web API smoke script
There’s a scripted smoke for the Stuart web API:

- `scripts/smoke_stuart_web_api_v1.sh`

---

### Docs worth reading (in this repo)

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

### Repo map (top-level)

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

## Roadmap

Future development plans include:

Core Platform

- stable Ashby runtime
- persistent environment state
- zone-based environment model

Modules

- camera intelligence
- inventory tracking
- energy monitoring
- environment control

Adapters

- Zigbee integrations
- Tuya integrations
- Home Assistant integrations
- direct IoT APIs

Interfaces

- voice interaction
- messaging interfaces
- mobile interfaces

---

## Contributing

Ashby is currently under active development.
Contributions will become easier once the runtime stabilizes.

---

## Philosophy

Ashby is built around one idea:

AI assistants should not just answer questions.
They should **operate systems**.

Ashby attempts to create a platform where AI can interact with the physical and digital world through structured modules and adapters.

---

## License
TBD
