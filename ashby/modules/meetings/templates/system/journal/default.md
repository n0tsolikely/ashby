---
template_version: 2
defaults:
  include_citations: false
  show_empty_sections: false
---

# Stuart v1 Journal Template (default)

This template defines the structure for JSON formalization output in journal mode.
The transcript (segment_id anchored) is the only source of truth.
DO NOT invent events, commitments, people, or conclusions.

## Header
Emit `header` with mode, retention, template_id, created_ts, and transcript_version_id when available.

## Narrative
Produce cleaned narrative sections with retention-governed detail.
NEAR_VERBATIM should stay closest to transcript phrasing while removing filler.

## Key Points
List key events/commitments grounded in transcript evidence.

## Feelings
Capture explicitly stated feelings only; do not infer emotions not present.

## Action Items
Capture explicit plans/tasks only; avoid invention.

## Citation Rules
Factual claims should be traceable to transcript segment_id anchors.
Whether citation tokens are rendered in MD is controlled separately by include_citations.
