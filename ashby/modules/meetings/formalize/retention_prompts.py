from __future__ import annotations

from ashby.modules.meetings.retention_registry import normalize_retention

# Edit these prompt blocks to tune retention behavior.
# Keep keys aligned with canonical retention values from retention_registry.
RETENTION_PROMPT_BLOCKS = {
    "LOW": (
        "Retention LOW: compress aggressively. Keep only the highest-signal facts, "
        "decisions, and actions that are explicitly supported by transcript evidence."
    ),
    "MED": (
        "Retention MED: balanced compression. Preserve key context and sequencing while "
        "removing repetition and filler."
    ),
    "HIGH": (
        "Retention HIGH: preserve most detail. Keep nuanced context and wording where it "
        "helps correctness, while still restructuring for clarity."
    ),
    "NEAR_VERBATIM": (
        "Retention NEAR_VERBATIM: stay close to transcript wording and order. Do minimal "
        "cleanup only; do not paraphrase away important phrasing."
    ),
}


def get_retention_prompt(retention: str) -> str:
    canonical = normalize_retention(retention)
    prompt = RETENTION_PROMPT_BLOCKS.get(canonical)
    if not prompt:
        raise ValueError(f"Unknown retention '{retention}' after normalization: {canonical}")
    return prompt

