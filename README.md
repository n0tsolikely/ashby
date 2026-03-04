# Ashby

Ashby is a **governed AI runtime system** designed to transform transcripts, sessions, and conversations into structured artifacts under strict operational governance.

Unlike typical AI applications, Ashby separates **runtime code** from **operational state**.
The system is controlled through a governance framework called **Synapse**.

---

# Repository Layout

Ashby operates as **two repositories**.

## Engine

```
github.com/n0tsolikely/ashby
```

Contains the runtime system:

```
Ashby_Engine/
```

Core responsibilities:

* API and service runtime
* transcription and diarization pipeline
* speaker map management
* formalization pipelines
* export bundle generation
* UI and API interfaces

The engine contains **no persistent operational state**.

---

## Governance / System State

```
github.com/n0tsolikely/Ashby_Data
```

Contains the canonical system state:

```
Ashby_Data/
```

This repository stores the artifacts that govern how the system evolves and executes.

### Major directories

#### Buffs

Startup configuration artifacts that define execution posture and system runtime rules.

#### Codex

Authoritative definition of the system:

* concepts
* workflows
* boundaries
* constraints

The Codex describes the system **as if it already exists**.

#### Quest Board

Work intake queue containing quests awaiting acceptance.

#### Guild Orders

Strategic objectives that define system development direction.

Guild Orders → Dungeons → Quests

#### Snapshots

Immutable historical records of system state and decisions.

Snapshots provide deterministic reconstruction of the system timeline.

#### Audits

Execution evidence generated when quests run.

Audits include logs, outputs, and receipts proving work occurred.

#### Latest Rehydration Pack

Artifacts required to restore the system state in a new session.

Includes:

* Bootstrap Prompt
* Continuity Lock
* Buffs
* Snapshot references

#### Talent Tree

Capability ledger proving system abilities through completed quests.

#### confirmations

Consent Gate artifacts that authorize high-risk operations.

---

# System Model

Ashby is governed through a structured workflow:

```
Guild Order
   ↓
Dungeon
   ↓
Quest
   ↓
Execution
   ↓
Audit
   ↓
Snapshot
```

This structure ensures all system work is:

* traceable
* auditable
* deterministic

---

# Runtime Architecture

The engine follows layered architecture:

```
ashby/
├ domain/
├ services/
├ adapters/
├ interfaces/
└ tests/
```

### Domain

Core system logic.

### Services

Workflow orchestration and business rules.

### Adapters

External integrations such as:

* LLM providers
* transcription engines
* storage systems

### Interfaces

System entry points:

* HTTP APIs
* UI interfaces
* gateway endpoints

---

# Formalization

Ashby converts transcripts into structured artifacts using LLMs.

Formalization outputs can include:

* meeting minutes
* structured summaries
* journals
* export bundles
* traceable document packages

Formalization is performed through a gateway service that connects the runtime to external model APIs such as Gemini.

---

# Execution Governance

Ashby does not execute work directly from prompts.

Execution requires governance artifacts.

Typical execution flow:

1. Control Sync determines scope
2. Quests are accepted from the Quest Board
3. Engine executes the work
4. Audits are written
5. Snapshots record system state

This approach prevents drift and preserves system continuity.

---

# Running the Engine

Requirements:

* Python 3.10+
* Linux / WSL recommended

Install:

```
git clone https://github.com/n0tsolikely/ashby.git
cd ashby

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the API:

```
uvicorn ashby.interfaces.web.app:app --host 0.0.0.0 --port 8000
```

Docs:

```
http://localhost:8000/docs
```

---

# System Smoke Tests

Ashby includes full system smoke tests verifying:

* session lifecycle
* transcription pipelines
* speaker map persistence
* formalization outputs
* export integrity
* UI constraints

Smoke test outputs are stored under:

```
docs/smoke_outputs/
```

---

# Project Status

Ashby is an actively evolving system controlled through Synapse governance.

Development occurs through artifact-driven workflows rather than traditional issue tracking.

---

# License

TBD
