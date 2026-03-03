from __future__ import annotations

from ashby.modules.meetings.formalize.retention_prompts import RETENTION_PROMPT_BLOCKS, get_retention_prompt


def test_all_canonical_retention_levels_exist_and_are_non_empty() -> None:
    for key in ("LOW", "MED", "HIGH", "NEAR_VERBATIM"):
        assert key in RETENTION_PROMPT_BLOCKS
        assert isinstance(RETENTION_PROMPT_BLOCKS[key], str)
        assert RETENTION_PROMPT_BLOCKS[key].strip()


def test_retention_aliases_normalize_to_canonical_prompt_blocks() -> None:
    near = get_retention_prompt("near-verbatim")
    assert near == RETENTION_PROMPT_BLOCKS["NEAR_VERBATIM"]
    med = get_retention_prompt("medium")
    assert med == RETENTION_PROMPT_BLOCKS["MED"]

