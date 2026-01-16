ASHBY — THE CANONICAL VISION
Version date: 2026-01-13
Canonical status: LOCKED (amend only via Control Sync)

Authoring context
This document is the single, human-readable, end-to-end explanation of Ashby as a platform.
It is meant to stand alone for a reader who has never seen the repo, the Codex, or any prior chat.
It explains what Ashby is, what problem it solves, how it works conceptually, what laws it obeys,
and how it expands safely over time without collapsing into a monolith.

This document is NOT a replacement for the Ashby Codex.
- The Codex is the binding implementation contract.
- The Preservation Packs embedded in the Codex are mechanical invariants (hard rules).
- This document is the “complete mental model”: the constitution + the shape + the intent.

Ashby canon hierarchy (practical):
1) Preservation Packs (mechanical invariants) — highest authority
2) Ashby Codex — binding law
3) Canonical Vision (this document) — human-readable constitution
4) Architecture Trees / Implementation Maps — repo-level structure contract
5) Control Sync Snapshots — decision history + locked pivots
6) Guild Orders — execution orders

If code contradicts this vision, either:
- the code is wrong, OR
- a Control Sync explicitly updated this vision and/or the Codex.

============================================================
0) The one-sentence definition
============================================================

Ashby is a local-first agentic platform that turns intelligence into reliable operations
by enforcing truth, state, policy, and execution contracts across removable modules and swappable adapters.

============================================================
1) What Ashby is (in plain language)
============================================================

Ashby is not “an assistant that talks.”
Ashby is an operating system for agency.

Ashby exists because natural language is not a system.
Language can express intent, but it cannot guarantee:
- what actually happened,
- what is currently true,
- what is safe to do next,
- what will remain true after a restart,
- or what is trustworthy enough to automate.

Ashby is the platform layer that makes intelligence accountable.

When you use Ashby, you are not asking for a conversational performance.
You are asking a system to:
- interpret an intent,
- constrain it with policy,
- execute through controlled interfaces,
- verify results as far as the environment allows,
- update durable state and artifacts,
- and speak only what is justified by evidence.

Ashby is designed for reality-touching domains where “sounding right” is not enough:
- home automation
- property monitoring
- incident logging
- meeting transcription and record generation (via modules like Stuart)
- business ops modules (inventory, workflows)
- any future domain where actions or records have consequences

============================================================
2) What Ashby is not
============================================================

Ashby is not:
- a wrapper around a large language model
- a chatbot with plugins
- a bundle of scripts glued together by vibes
- a monolithic god-file (“main.py becomes the brain”)
- a vendor-controlled cloud service pretending to be local
- a system that guesses when uncertain

Ashby refuses to become:
- a lie engine (confident claims without proof)
- an account-coupled monolith (where the vendor defines reality)
- a brittle integration pile (where adding a device breaks everything)
- a fragile online service (where the internet is required for agency)
- a “smart home app” that only works when the cloud is happy

============================================================
3) The core problem Ashby exists to solve
============================================================

Most assistants fail in predictable ways:

1) They treat language as truth.
They say “Done,” “It’s on,” “All set,” even when:
- the call failed,
- the device is unreachable,
- state is stale,
- the assistant is guessing.

2) They treat state as a vibe.
They infer “what must be true” from chat history instead of maintaining an explicit world model.
They collapse the moment reality changes outside the chat.

3) They are vendor-shaped.
They inherit vendor semantics and vendor outages as “reality.”
They become dependent on vendor accounts for identity and truth.

4) They cannot explain themselves.
When something breaks, there is no traceable chain of:
intent → policy → action → result → state update → response.

5) They die from growth.
As features accumulate:
- boundaries blur,
- exceptions multiply,
- shortcuts become permanent,
- core files swell,
- understanding erodes.

Ashby exists to solve all five permanently by making truth and state first-class and enforced by law.

============================================================
4) The constitution (non-negotiables)
============================================================

Everything below is law. These are structural constraints, not preferences.

4.1 Commandment I — Ashby does not lie
Ashby never claims an action occurred without evidence.
Ashby never reports current state as fact without verification boundaries.
Ashby never smooths partial success into full success.
Ashby never reconstructs continuity after failure as if nothing happened.

If Ashby cannot verify an outcome, it must say so explicitly.

4.2 Commandment II — Ashby does not guess
Ashby does not fill gaps in knowledge with assumptions presented as facts.
If something is unknown, it is spoken as unknown.
If continuity is uncertain after restart, it is spoken as uncertain.

Ashby can propose hypotheses and next steps.
Ashby cannot pretend it knows.

4.3 Commandment III — Ashby owns truth, not vendors
Vendors can execute commands and provide telemetry.
Vendors do not define Ashby’s world model.

Ashby must remain capable of:
- admitting vendor uncertainty,
- surviving vendor outages,
- migrating vendors without rewriting platform truth semantics.

4.4 Commandment IV — Ashby separates WHAT from HOW
WHAT = intent, meaning, policy, state transitions, truth semantics, user-facing behavior.
HOW = vendor APIs, device protocols, execution adapters, connectors, transports.

This boundary is absolute.
Vendor code never belongs inside domain logic.
Domain semantics never belong inside adapters.

4.5 Commandment V — Ashby remains removable
Modules are removable organs.
Remove lights and Ashby still runs.
Remove a vendor integration and Ashby degrades honestly.
Remove devices and the system still answers without corrupting itself.

Removability is the proof Ashby is a platform, not a pile of features.

4.6 Commandment VI — Ashby remembers
Ashby’s memory is explicit and durable.
Chat history is not memory.
Artifacts and state models are memory.

Ashby must remain accountable across restarts.

4.7 Commandment VII — Ashby explains itself
Ashby can always answer:
- what it did,
- why it did it,
- what evidence it used,
- what it is unsure about,
- why it failed,
- and what the next safe action is.

If the system cannot explain itself, it cannot be trusted.

4.8 Commandment VIII — Ashby survives growth
Ashby grows through controlled seams.
New capability arrives as modules and adapters, not as core rewrites.
Core law remains stable under feature expansion.

4.9 Commandment IX — Ashby is offline-capable
Ashby must be capable of operating without internet access when paired with appropriate hardware.
Connectivity is optional capability, not a platform dependency.
Cloud is allowed as a profile, not as a requirement.

4.10 Commandment X — Ashby treats humans safely
Safety includes:
- physical safety (devices, automation)
- cognitive safety (no deceptive certainty)
- psychological safety (no manipulative language)
- operational safety (no unstoppable automation)

Ashby prefers refusal/clarification over unsafe autonomy.

============================================================
5) The platform anatomy (Ashby as a body with organs)
============================================================

Ashby is a body.

The body (platform core) includes:
- Router / Orchestrator (thin)
- Policy & permissions
- Truth Gate (response constraints)
- State model (beliefs with confidence and staleness)
- Storage abstraction (read/write boundaries)
- Logging and observability
- Scheduler / Job Queue (“watchers”)
- Evaluation harness (regression immunity)
- Identity (user identity, scope identity, module identity)
- Registries (modules/adapters/entities)

Organs are modules and agents:
- lights module
- comfort module
- cameras module
- irrigation module
- meetings module (Stuart)
- inventory module (Tori)
- future modules not yet named

Ashby does not “become” modules.
Ashby hosts them under one shared law system.

============================================================
6) Canonical objects (what Ashby is made of)
============================================================

These objects are the stable spine of the platform.

6.1 Request Envelope
Transport-level capture.
Contains:
- user_id
- raw text (or structured input)
- channel (cli/telegram/api)
- timestamp
- correlation_id
Transport does not interpret. It only captures.

6.2 Intent Record (WHAT request)
Structured representation of user intent.
Contains:
- intent type (domain.action)
- target set (zones/devices/entities)
- canonical parameters (brightness, temperature, on/off, etc.)
- ambiguity markers + confidence
- provenance (user_id, correlation_id, requested_at)

Intent is a request, not a plan.

6.3 Policy Decision (platform adjudication)
A central decision that constrains what can happen next.
Canonical outcomes:
- ACT
- CLARIFY
- CONFIRM
- REFUSE
- DEFER (schedule/queue)
- NO-OP

Policy is not owned by modules.
Modules may provide domain-specific risk context, but the platform decides.

6.4 Action Plan (executable steps)
A structured plan derived from intent + policy.
Contains:
- tool calls (adapter operations)
- expected effects
- blast radius boundaries
- verification expectations (if supported)

Plans are explicit so they can be audited.

6.5 Action Result (ActionResult)
The primary truth object for actions.
Contains:
- attempted targets
- succeeded targets
- failed targets + structured error objects
- verification class (verified / last_known / unknown)
- raw adapter responses (sanitized)
- timestamps and correlation_id

ActionResult is “reality as observed by execution.”

6.6 State Beliefs (WorldState / HouseState)
State is represented as belief with explicit evidence.
Each belief contains:
- value
- confidence
- last_updated
- evidence reference (ActionResult, telemetry, user assertion)
- decay/staleness semantics

State is not “what the assistant said last.”
State is what can be justified.

6.7 Artifacts (durable records)
Artifacts are canonical memory.
They are produced by modules, stored durably, and readable even if a module is removed.
Examples:
- meeting transcripts, minutes, evidence maps
- incident reports
- audit logs
- configuration snapshots

6.8 Scope Graph (Zones generalized)
A domain-independent hierarchy of scopes:
- property/home
- floor
- room/zone
- group
- device
- subcomponents (channels/sensors)

Scopes prevent chaos and enable consistent target resolution.

6.9 Registries
Ashby maintains registries for:
- modules (module_key, version, capabilities, dependencies)
- adapters (adapter_key, capabilities, verification support)
- entities/devices (device_key, type, vendor mapping, scope placement)
- profiles (what’s enabled/allowed)
Registries prevent implicit drift.

============================================================
7) The execution pipeline (end-to-end)
============================================================

Ashby’s runtime is a pipeline, not a brain blob.

Canonical high-level flow:

1) Transport capture
- CLI / Telegram / local API / future web UI
- captures text + metadata
- does not execute domain logic

2) Normalize into Request Envelope
- attach user_id + correlation_id
- ensure stable metadata shape

3) NLU / intent extraction
- convert raw text into an Intent Record
- mark ambiguity explicitly (do not hide it)

4) Target resolution (scope graph + registry)
- resolve “bedroom” → zone_id
- resolve “the lamp” → device_key
- compute blast radius (how many devices will be affected)

5) Policy decision
- ACT / CLARIFY / CONFIRM / REFUSE / DEFER / NO-OP
- enforce permissions, profile constraints, safety gates

6) Router dispatch (thin)
- pick module by intent type
- call module handler/service
- router does not “interpret meaning”; it only orchestrates

7) Module interpretation (domain semantics)
- module converts intent into:
  - Action Plan (for execution modules), OR
  - Pipeline Run Plan (for compute modules), OR
  - Clarification payload

8) Tool runtime execution (adapters)
- perform HOW via adapters
- return structured results

9) Verification + state update
- update beliefs
- handle staleness
- preserve partial success

10) Truth Gate
- constrain language based on evidence classes

11) Response rendering
- response must match truth posture
- include mixed outcomes explicitly
- include next safe actions (refresh, clarify, confirm)

12) Logging and audit
- write the trace for accountability and debugging

The router stays thin.
If router logic starts looking like “the brain,” the platform is broken.

============================================================
8) Action-Gated Truth (Ashby’s speech law)
============================================================

Ashby’s language is constrained by truth posture. This is not style. It is safety law.

8.1 VERIFIED language
Use VERIFIED only when Ashby has verified evidence that an outcome occurred.
Verification sources include:
- direct readback (device reports state)
- sensor confirmation
- trusted telemetry that is known to be reliable
- deterministic artifacts produced by a pipeline stage (for compute modules)

VERIFIED language must not appear when verification is missing.

8.2 LAST_KNOWN language
Use LAST_KNOWN when Ashby executed an action successfully but lacks verification.
This preserves accountability without lying.

LAST_KNOWN must:
- clearly state the uncertainty
- avoid “done” language
- offer a next step (refresh/verify) when possible

8.3 UNKNOWN language
Use UNKNOWN when Ashby has no basis to know.
UNKNOWN is honesty, not weakness.

8.4 FAILED language
Use FAILED when execution failed.
FAILED must include:
- what was attempted
- what failed
- why (error object)
- next safe step

8.5 NO-OP handling
Sometimes nothing changes.
Ashby must be allowed to say:
- “No change needed; it was already set.”
NO-OP prevents busywork and prevents forced lying.

8.6 Forbidden phrase principle
Certain phrasing is forbidden because it launders uncertainty into confidence.
The exact list is maintained in the Codex/Truth Gate Preservation Pack.
The platform must enforce it mechanically.

============================================================
9) State as belief (remembering without hallucinating)
============================================================

Ashby models state as belief with evidence and decay.

9.1 Belief vs fact
- Fact: verified now.
- Belief: inferred from evidence that may go stale.

Ashby must not speak beliefs as facts without a qualifier.

9.2 Confidence is evidence confidence
Confidence is based on:
- verification quality
- time since last verification
- known reliability of the integration
- contradictions (user asserts something different, telemetry disagrees)

9.3 Staleness and decay
Every belief decays.
When stale, Ashby must downgrade confidence and truth posture.

9.4 Partial success and mixed reality
Mixed outcomes are normal:
- some devices succeed, others fail
- some zones update, others are unreachable

Ashby must never collapse mixed outcomes into “done.”

9.5 Restart discipline
After restart, Ashby must not pretend continuity.
If state cannot be refreshed, Ashby degrades to LAST_KNOWN or UNKNOWN.

============================================================
10) Sessions (coherence + safety)
============================================================

Sessions are a safety and coherence mechanism.

A session is a scoped unit of ongoing intent:
- who is being controlled
- which scope is active
- what clarifications are pending
- what jobs are running
- what the user is currently focused on

Sessions prevent:
- ambiguous pronoun disasters (“turn it off”)
- stale context controlling reality
- accidental blast radius expansion

Canonical session archetypes:

10.1 Lights-style sessions
- active zone/devices persist for follow-ups
- “dim them” resolves inside the session scope

10.2 Time-bound control sessions
- irrigation timers, schedules
- explicit expiry rules
- job queue integration

10.3 Comfort sessions
- comfort state is persistent but staleness-aware
- can degrade to unknown if telemetry unreliable

10.4 Pending clarification sessions
- session holds a structured question + candidate targets
- resolution is explicit and logged

10.5 Expiry and safety
Sessions expire by default.
Expiry rules are domain-specific but mandatory.

============================================================
11) Modules (meaning without polluting core)
============================================================

A module is a governed unit of meaning and capability.

11.1 Responsibilities
Modules:
- interpret domain semantics
- produce action plans or pipeline runs
- produce artifacts in canonical formats
- remain auditable
- remain removable

11.2 Prohibitions
Modules must never:
- execute vendor calls directly
- store secrets
- bypass policy outcomes
- decide truth class
- invent verification
- create hard dependencies that prevent removal

11.3 Lifecycle obligations
Modules must support:
- install, enable/disable, upgrade, deprecate, remove
- manifest + capability declarations
- compatibility declarations (interfaces required)
- migration notes when state meaning changes

11.4 Removability guarantees
Removing a module must not:
- corrupt core
- orphan schedules that continue running
- erase history silently
- make old artifacts unreadable

============================================================
12) Adapters (HOW the platform touches reality)
============================================================

Adapters are the execution boundary.
They do HOW, never WHAT.

12.1 Responsibilities
Adapters:
- perform vendor/protocol operations
- return structured outcomes
- expose verification/telemetry when possible
- remain replaceable without rewriting domain logic

12.2 Prohibitions
Adapters must never:
- interpret natural language
- decide policy outcomes
- hide failures
- fabricate success
- leak secrets into logs/artifacts
- encode product-tier behavior

12.3 Offline-first preference
Local execution is preferred.
Cloud is allowed only as a profile and must be disclosed + consented.

12.4 Verification responsibility
If verification is possible, adapters must expose it.
If verification is not possible, adapters must admit it.
Verification is not optional; it is part of the interface contract.

============================================================
13) Policies, permissions, and confirmations
============================================================

Policy is centralized law.

13.1 Permissions
Permissions are evaluated based on:
- user identity
- scope identity (which home/property)
- module entitlements (what modules are enabled)
- environment profile (LOCAL_ONLY/HYBRID/CLOUD)

13.2 Confirmations
Ashby must request confirmation when:
- blast radius is large
- safety risk is non-trivial
- the user’s request is ambiguous
- the request touches sensitive scopes
- the profile would require sending data externally

Confirmations are explicit and logged.

13.3 Refusals
Ashby must refuse when:
- the request is out of scope
- it violates safety policy
- it violates permissions/entitlements
- execution seams are not configured

Refusal is honesty, not failure.

============================================================
14) Storage, artifacts, and persistence
============================================================

Ashby treats storage as a contract.

14.1 Storage abstraction
All reads/writes go through a storage adapter boundary.
Paths are deterministic.
Writes are auditable.

14.2 Runtime vs canonical artifacts
Runtime:
- caches
- ephemeral sessions
- job queue state
- transient telemetry

Canonical artifacts:
- transcripts, evidence maps, PDFs
- incident reports
- audit logs
- configuration snapshots

Artifacts are what survive.
Artifacts are what build trust.

14.3 No silent overwrites
Ashby preserves history.
If state changes, the change is recorded with provenance.

============================================================
15) Observability (logs, traces, audit)
============================================================

If Ashby cannot be audited, it cannot be trusted.

15.1 Correlation IDs
Every request carries a correlation_id.
Every tool call, ActionResult, and response carries it.

15.2 Structured logging
Logs are structured, not narrative.
They include:
- stage
- module_key
- adapter_key
- outcome
- timings
- error objects
- verification class

15.3 Audit log
Reality-touching actions are auditable by default.
The platform can answer:
“What happened at 3:12pm and why?”

============================================================
16) Scheduler and watchers (time + sensors)
============================================================

Ashby is not only reactive.
It is allowed to watch and act over time, safely.

16.1 Scheduler
A scheduler allows:
- delayed execution (“turn off in 30 minutes”)
- recurring jobs (“every day at 10pm”)
- maintenance tasks (refresh device states)

16.2 Watchers
Watchers are jobs triggered by:
- time
- sensor events
- state thresholds

Examples:
- “If motion detected after 11pm, alert me.”
- “If temperature drops below 60°F, turn on heat.”
- “Every morning, refresh critical device states.”

16.3 Safety constraints
Watchers must:
- have explicit scope boundaries
- be pausable/killable
- log every execution with ActionResults
- degrade safely if telemetry is stale

============================================================
17) Evaluation and regression harness (immune system)
============================================================

Ashby must be testable in the same path it runs in production.

17.1 Scenario tests are regression locks
They lock:
- truth gating
- policy decisions
- session behavior
- mixed outcomes
- module removability

17.2 No bypassing core in tests
Tests must exercise:
transport → router → module → adapters → truth gate.
Test-only shortcuts invalidate results.

17.3 Golden data
For compute modules (meetings), golden transcripts and evidence maps anchor regressions.

============================================================
18) Multi-agent futures (Ashby as a host)
============================================================

Ashby is designed to host multiple agents without core contamination.

18.1 Shared core, separate organs
Agents share:
- router
- policy
- truth gate
- state model
- logging
- security
- permissions
Agents do not share:
- private storage keys
- internal pipelines
- hidden state semantics

18.2 Stuart as a first-class hosted agent
Stuart is the meetings module.
It produces durable artifacts that become part of Ashby memory.
Stuart does not bypass platform law.
Stuart’s evidence maps act as “truth objects” for generated meeting records.

18.3 Conflict arbitration
When agents disagree, Ashby arbitrates via:
- evidence hierarchy
- timestamps
- staleness/decay semantics
- explicit user confirmation when necessary

============================================================
19) Growth strategy (how Ashby expands without collapsing)
============================================================

Ashby grows through controlled seams.

19.1 Bridge-first strategy
Bridges integrate external systems temporarily.
Bridges are not allowed to become core truth.
Bridges are transitional and must remain replaceable.

19.2 Home Assistant as strangler layer (example)
Home Assistant may provide early device access.
Ashby treats it as a bridge until native adapters exist.

19.3 Protocol bridges (Zigbee, Matter)
Protocol-level adapters remain behind interfaces.
No protocol code leaks into domain logic.

19.4 Native vendor expansion
Vendor adapters are added without rewriting domain logic.

19.5 Profiles vs forks
Profiles enable/disable modules and adapters.
Profiles must never fork the engine.

19.6 Feature flags and entitlements
Flags stage rollout; they do not create hidden laws.
Entitlements control access; they do not create divergent behavior semantics.

============================================================
20) Product surfaces (how humans use Ashby)
============================================================

Transport is not the product.
Transport is how the product is accessed.

Ashby supports:
- CLI (developer/operator)
- Telegram (fast iteration, remote text)
- Local API (future)
- Web UI (pinned for later; must remain a client of the local instance)
- Voice (postponed until policy/stance is stable)

The product is the engine.

============================================================
21) Canonical repository shape (engine layout vision)
============================================================

Ashby must have a filesystem structure that prevents god files and prevents boundary collapse.

End-state (conceptual, not exact filenames):

/ashby/
  core/            # router, policy, truth gate, scheduler, registry, storage abstraction
  interfaces/      # stable contracts for adapters/modules/tools
  adapters/        # vendor/protocol implementations (HOW)
  modules/         # domain modules/agents (WHAT interpretation)
  evaluation/      # harness + scenario tests + golden data utilities
/io/
  cli/
  telegram/
  api/             # future local HTTP API
/configs/          # declarative configuration schemas and instances
/runtime/          # local-only state, caches, artifacts
/secrets/          # redacted placeholders only (real secrets never in repo)
/tests/            # test runner entrypoints and fixtures

Rules:
- No vendor code outside adapters/
- No circular imports
- Router reads like a pipeline, not a brain
- Modules depend on interfaces, not on adapters directly
- Adapters depend on interfaces, not on modules
- Core depends on interfaces, not on specific adapters

============================================================
22) Required build order (how to rebuild without cheating)
============================================================

Ashby is rebuilt by restoring invariants in dependency order.

The order is conceptually:

1) Core truth law (ActionResult-as-reality + Truth Gate constraints)
2) Core state law (beliefs, staleness, decay, mixed reality)
3) Core policy and permissions (act/clarify/confirm/refuse)
4) Core routing discipline (thin router, module dispatch)
5) Storage abstraction and audit logging
6) Scope graph + entity registry
7) Evaluation harness (regression immunity)
8) Scheduler/watchers (time + sensors)
9) Modules and agents (lights, comfort, meetings/Stuart, inventory/Tori)
10) Product surfaces (web UI, voice)

If you invert the order, you get a system that “works” while silently lying.

============================================================
23) Completion definitions (what “done” means)
============================================================

Ashby is never “feature complete.”
It becomes “platform complete” when core invariants are stable and enforceable.

Platform-complete means:
- truth gating is enforced mechanically
- state model is explicit and staleness-aware
- modules are removable without corrupting core
- adapters are swappable without rewriting domain logic
- policy decisions are centralized and auditable
- evaluation harness prevents regressions
- offline-first is real, not marketing

============================================================
24) The promise of Ashby
============================================================

Ashby promises:
- honesty under uncertainty
- agency without deception
- modular growth without collapse
- offline-capable operation
- auditability and explainability
- safe interaction with reality

Ashby refuses to become:
- a confident liar
- a brittle vendor shell
- a monolith
- a black box

Ashby is built to be rebuilt.
Ashby is built to survive.

============================================================
25) Security & secrets (non-negotiable operational law)
============================================================

Security in Ashby is not “enterprise fluff.”
It is required because Ashby touches reality and stores durable memory.

Ashby security principles:

25.1 Secrets never live in code
- No API keys, tokens, passwords, or private URLs in the repo.
- No secrets in commits.
- No secrets in screenshots, logs, or transcripts.

If a secret is ever committed, treat it as burned:
- rotate/revoke immediately
- remove from history if necessary
- treat every artifact that contains it as compromised

25.2 Redacted placeholders are allowed
The repo may contain redacted templates that document:
- what kind of secret is needed
- where it should live (path / env var name)
- required scopes/permissions
- example shape with REDACTED values

25.3 Runtime secret loading is explicit
Secrets are loaded at runtime via a secrets adapter or environment injection.
Modules do not fetch secrets.
Adapters do not embed secrets.

25.4 Least privilege
Each adapter integration should have the minimum permissions needed.
If an adapter only needs read state, it should not have write permissions.

25.5 Transport is not trusted
Telegram/CLI messages are not trusted “authority.”
Authority is derived from:
- user identity mapping
- permissions
- scope boundaries
- confirmation rules

============================================================
26) Configuration law (no invisible behavior)
============================================================

Configuration must be explicit, typed, and readable.

26.1 Config schemas exist before config instances
Every meaningful config file must have a schema:
- required fields
- allowed values
- defaults
- validation rules
This prevents “mystery behavior” driven by untyped config drift.

26.2 Config is declarative
Config declares:
- which modules exist
- which adapters are available
- which entities/devices are registered
- which scopes/zones exist
- which profiles are enabled
Config does not embed code.

26.3 Profiles are configuration, not forks
A profile is an activation matrix:
- enabled modules
- allowed adapters
- consent requirements
- safety thresholds
Profiles do not create new laws.
They choose which organs are connected.

============================================================
27) Interface contracts (the handshake that prevents refactors)
============================================================

Ashby survives growth by enforcing stable interfaces.

27.1 Core ↔ Module contract
Modules interface with core via:
- IntentRecord in
- PolicyDecision in
- ActionPlan / ClarifyPayload out
- Artifact manifests out (for compute modules)
Modules do not call adapters directly unless the interface explicitly allows it through tool runtime.

27.2 Core ↔ Adapter contract
Adapters interface with core via:
- ToolCall in (structured, validated)
- ToolResult out (structured, typed, sanitized)
Adapters must return enough structure for:
- partial success representation
- verification class assignment
- error taxonomy

27.3 Response generation contract
User-facing language is generated from truth objects:
- ActionResults
- verified telemetry
- canonical artifacts
Never from intent alone.

============================================================
28) Migration & structural realignment (how Ashby evolves safely)
============================================================

Ashby is designed to be rebuilt and restructured without losing truth.

28.1 Structural raids are allowed
Ashby may undergo structural refactors that change file placement and naming.
These refactors must be:
- mechanical
- behavior-preserving
- auditable
- reversible

28.2 Schema migrations are explicit
If a state or artifact schema changes:
- the change is versioned
- a migration path exists OR old artifacts remain readable forever
- migrations are rehearsed under the evaluation harness

28.3 “No silent rewrite” rule
You never silently rewrite history.
You produce a new artifact/run, or a migration artifact, and preserve lineage.

============================================================
29) HouseState sync & staleness discipline (living with unreliable reality)
============================================================

Reality is messy. Devices lie. Networks fail. Vendors drift.

Ashby survives by treating state as a living belief model.

29.1 Sync is deliberate
State sync happens via:
- periodic refresh jobs
- event-driven telemetry (if available)
- explicit user refresh requests

29.2 Staleness windows are per-attribute
“Bedroom lights on/off” may have a different decay window than “thermostat temperature.”
Staleness must be defined per domain and per attribute.

29.3 Contradictions are first-class
If the user says “the lights are off” but telemetry says “on,” Ashby records a contradiction.
Ashby does not pick a side silently.
It offers verification or asks the user to clarify.

============================================================
30) Appendix — Example end-to-end flows (how the laws show up in real usage)
============================================================

30.1 Lights control (reactive)
User: “Turn off the bedroom lights.”

- Transport creates Request Envelope (user_id, correlation_id).
- NLU creates IntentRecord:
  - intent: lights.set_state
  - target: zone “bedroom”
  - params: power=off
- Target resolution expands zone to device_keys.
- Policy evaluates:
  - blast radius (how many lights)
  - permissions (allowed)
  - safety gates (ok)
  - decision: ACT
- Router dispatches to lights module.
- Module produces ActionPlan with tool calls.
- Tool runtime executes adapter calls.
- ActionResults returned:
  - succeeded: [lamp_1, ceiling_2]
  - failed: [strip_4 unreachable]
  - verification: LAST_KNOWN (if no readback) or VERIFIED (if readback supported)
- Truth Gate produces response:
  - “I sent the command to turn off the bedroom lights. Two responded; one didn’t. Want me to refresh?”

Notice what Ashby does NOT do:
- It does not say “Done” when one device failed.
- It does not pretend the lights are off if it can’t verify.

30.2 Meeting transcription (heavy compute via Stuart)
User: “Transcribe this recording and generate minutes.”

- Transport captures file upload / reference.
- Policy requires explicit run confirmation (compute + artifacts).
- Router dispatches to meetings module (Stuart).
- Stuart runs pipeline and produces artifacts:
  - transcript.json
  - evidence_map.json
  - minutes.md
  - minutes.pdf
- Truth Gate allows declarative claims only when backed by evidence pointers:
  - decisions/actions in minutes must cite transcript segments.

Ashby can safely “remember” these outcomes because they are artifact-backed, not vibes.

30.3 Camera watcher (sensor-driven)
Watcher: “If motion after 11pm, alert me.”

- Scheduler triggers watcher based on time + sensor events.
- Policy enforces safety: alert-only vs action.
- Adapter provides telemetry event.
- Ashby produces an audit trail of the watcher run:
  - event received
  - decision (alert)
  - action (send notification)
  - outcome

============================================================
31) Appendix — Canonical anti-patterns (things that kill Ashby)
============================================================

If any of these appear, the architecture is drifting:

- Router file becomes “the brain”
- Module imports a vendor SDK directly
- Adapter interprets natural language
- A “quick hack” writes directly to runtime state without a schema
- “Done” language appears without verification
- State is inferred from chat history
- Feature work requires editing many unrelated modules (boundary collapse)
- Removing a module breaks unrelated domains (non-removable core contamination)
- Tests bypass truth gate or policy for convenience

These are not stylistic issues. They are existential.

END OF ASHBY — THE CANONICAL VISION
