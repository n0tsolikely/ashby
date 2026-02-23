from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


# v1-only, enumerated. Do not add new retention levels without Control Sync + quest.
_ALLOWED_CANONICAL: List[str] = [
    "LOW",
    "MED",
    "HIGH",
    "NEAR_VERBATIM",
]

# Aliases that normalize into canonical retention levels.
_ALIASES: Dict[str, str] = {
    "LOW": "LOW",
    "MED": "MED",
    "MEDIUM": "MED",
    "HIGH": "HIGH",
    "NEAR_VERBATIM": "NEAR_VERBATIM",
    "NEAR-VERBATIM": "NEAR_VERBATIM",
    "NEAR VERBATIM": "NEAR_VERBATIM",
    "NEARVERBATIM": "NEAR_VERBATIM",
}


@dataclass(frozen=True)
class RetentionValidation:
    ok: bool
    raw: str
    canonical: Optional[str]
    allowed: List[str]
    message: Optional[str] = None


def allowed_retentions() -> List[str]:
    # copy to prevent mutation
    return list(_ALLOWED_CANONICAL)


def normalize_retention(raw: str) -> str:
    s = (raw or "").strip().upper()
    s = s.replace("-", "_")
    s = "_".join([p for p in s.split() if p])
    return _ALIASES.get(s, s)


def default_retention() -> str:
    return "MED"


def validate_retention(raw: str) -> RetentionValidation:
    n = normalize_retention(raw)
    allowed = allowed_retentions()

    if n in allowed:
        return RetentionValidation(ok=True, raw=raw, canonical=n, allowed=allowed)

    msg = f"Unknown retention '{raw}'. Allowed: {', '.join(allowed)}."
    return RetentionValidation(ok=False, raw=raw, canonical=None, allowed=allowed, message=msg)
