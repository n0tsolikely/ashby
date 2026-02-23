# Stuart Transcript Versioning Model v1

## TranscriptVersion artifact
- Transcript versions are immutable, write-once artifacts.
- Canonical fields:
  - `transcript_version_id` (`trv_*`)
  - `session_id`
  - `run_id`
  - `created_ts`
  - `diarization_enabled`
  - `asr_engine`
  - `audio_ref`
  - `segments`
- A transcript version is never edited in place. Any correction flow must create a new artifact.

## Runtime storage layout
- Session index: `sessions/{session_id}/transcripts/index.jsonl`
- Version artifacts: `sessions/{session_id}/transcripts/versions/{transcript_version_id}.json`
- Global lookup: `transcript_versions/lookup.jsonl`

## Active transcript pointer semantics
- Session pointer lives in `sessions/{session_id}/session_state.json` as:
  - `active_transcript_version_id`
- Pointer updates are mutable state updates only.
- Transcript version artifacts remain immutable.

## API endpoints
- `GET /api/sessions/{session_id}/transcripts`
  - Metadata list only (no full segments payload).
  - Includes `active` marker based on `session_state.active_transcript_version_id`.
- `GET /api/transcripts/{transcript_version_id}`
  - Returns full transcript version payload, including segments and metadata.
- `PATCH /api/sessions/{session_id}/transcripts/active`
  - Payload: `{ "transcript_version_id": "trv_..." }`
  - Pointer-only update; does not mutate transcript artifacts.

## Formalize transcript selection order
- Formalize selection rule:
  1. explicit `transcript_version_id` in run/formalize params
  2. `session_state.active_transcript_version_id`
  3. legacy fallback (`reuse_run_id` / legacy run transcript linkage)

## Forward notes
- Dungeon 5 will wire real ASR + diarization toggle into transcript version emission.
- Any future transcript correction model must be additive:
  - new transcript version artifact(s)
  - never mutate prior transcript versions.
