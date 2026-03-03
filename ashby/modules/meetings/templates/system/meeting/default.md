---
template_version: 2
defaults:
  include_citations: false
  show_empty_sections: false
---

# Stuart v1 Meeting Template (default)

This template defines the structure for JSON formalization output in meeting mode.
The transcript (segment_id anchored) is the only source of truth. DO NOT invent.

## Header
Emit `header` with mode, retention, template_id, created_ts, and transcript_version_id when available.

## Participants
List only transcript-grounded participants; no invented names or attendance.

## Topics Discussed
Capture concrete topics with summaries grounded in transcript segment_id evidence.

## Decisions
Only include explicit commitments/agreements. If not explicit, omit.

## Action Items
Only include explicitly assigned actions. If assignee unknown, set as unassigned.

## Notes / Discussion
Capture important supporting detail with retention-governed depth.

## Open Questions / Risks
Capture unresolved items and known risks only when present in transcript.

## Citation Rules
Every factual claim must be traceable to transcript segment_id anchors.
Whether citation tokens are rendered in MD is controlled separately by include_citations.
