from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict

from ashby.modules.meetings.formalize.retention_prompts import get_retention_prompt
from ashby.modules.meetings.schemas.artifacts_v1 import dump_json


def _policy_sha256(retention: str) -> str:
    policy = get_retention_prompt(retention)
    return hashlib.sha256(policy.encode("utf-8")).hexdigest()


def write_llm_usage_receipt(
    *,
    artifacts_dir: Path,
    provider: str,
    model: str,
    request_id: str,
    timing_ms: int,
    usage: Dict[str, Any],
    retention: str,
) -> Path:
    out = artifacts_dir / "llm_usage.json"
    payload = {
        "version": 1,
        "provider": provider,
        "model": model,
        "request_id": request_id,
        "timing_ms": timing_ms,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "char_count": usage.get("char_count"),
        },
        "retention": retention,
        "policy_sha256": _policy_sha256(retention),
    }
    dump_json(out, payload, write_once=True)
    return out

