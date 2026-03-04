# Full System Smoke Test (D12)

This document mirrors `scripts/full_system_smoke_test.sh` phase order.

## Output Contract

All captured output is written under:

- `docs/smoke_outputs/<YYYY-MM-DD>/run.log`

Later D12 quests add:

- `docs/smoke_outputs/<YYYY-MM-DD>/artifacts_list.txt`
- `docs/smoke_outputs/<YYYY-MM-DD>/export_list.txt`

## Fixture Inputs

- `tests/fixtures/stuart_smoke/meeting_fixture_3speakers_36s.wav`
- `tests/fixtures/stuart_smoke/journal_fixture_1speaker_42s.wav`
- `tests/fixtures/stuart_smoke/fixture_manifest.json`

## Phase Order

1. Start server
2. Create session(s)
3. Upload fixture audio
4. Transcribe (diarize ON/OFF)
5. Map speakers
6. Formalize (DEFAULT_TEST_TEMPLATE)
7. Session chat hard-lock checks
8. Global chat cold-start checks
9. Root UI surface check
10. Export bundle checks

## QUEST_198 Scope

`QUEST_198` provides phase scaffolding and output path contract only.
Behavioral assertions and end-to-end checks are implemented in subsequent D12 quests.

## QUEST_200 Scope Update

`QUEST_200` implements real execution for:

1. Start server (reachability check + optional backend autostart)
2. Create session(s) (meeting + journal)
3. Upload fixture audio (meeting + journal)

Remaining phases are intentionally marked pending for later D12 quests.

## QUEST_201 Scope Update

`QUEST_201` implements:

4. Transcribe meeting fixture with diarization ON and OFF
5. Poll run status to terminal state for both runs
6. Assert transcript version count is at least two for the meeting session

## QUEST_202 Scope Update

`QUEST_202` implements:

7. Resolve diarized transcript version ID from transcript list
8. Persist speaker map overlay via transcript speaker_map endpoint
9. Read back and assert overlay persistence without re-transcribe

## D12 Completion Scope (QUEST_203-QUEST_207)

The canonical smoke script now validates all D12 phases end-to-end:

1. Formalization metadata + PDF checks (meeting + journal)
2. Session chat hard-lock and no-cross-session leakage behavior
3. Global chat cold-start hits/actions/citations contract
4. Frontend root UI surface check (Vite/React root only; no legacy backend surface)
5. USER export variants (full/transcript-only/formalization-only) with format filters
6. DEV export structure checks with absolute path hygiene

Additionally, each run writes:

- `docs/smoke_outputs/<YYYY-MM-DD>/run.log`
- `docs/smoke_outputs/<YYYY-MM-DD>/artifacts_list.txt`
- `docs/smoke_outputs/<YYYY-MM-DD>/export_list.txt`

## Rerun Guidance

Run baseline LOCAL_ONLY smoke:

```bash
cd /home/notsolikely/Ashby_Engine
STUART_SMOKE_USE_MINI_FIXTURES=1 \
ASHBY_ASR_ENABLE=0 \
STUART_SMOKE_AUTOSTART_BACKEND=1 \
STUART_SMOKE_AUTOSTART_FRONTEND=1 \
bash scripts/full_system_smoke_test.sh
```

If running from governed quest execution, use the quest wrapper command and record receipts to the active audit bundle.

## Failure Interpretation

- `FAIL: backend startup failed`: backend did not become reachable on `127.0.0.1:8844`.
- `session_chat_*` errors in Phase 7: session-scope hard lock/citation truth gate contract regressed.
- `global_chat_*` errors in Phase 8: global chat envelope/actions/citation contract regressed.
- `root_ui_surface_*` errors in Phase 9: frontend root no longer exposes canonical React/Vite surface.
- `export_bundle_*` errors in Phase 10: export structure/filter/path-hygiene contract regressed.

When failures occur, inspect:

- `docs/smoke_outputs/<YYYY-MM-DD>/run.log`
- `/tmp/stuart_smoke_backend.log`
- `/tmp/stuart_smoke_frontend.log` (if frontend autostarted)
