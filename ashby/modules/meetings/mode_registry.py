from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Union

# v1-only, enumerated. Do not add new modes without Control Sync + quest.
_ALLOWED_CANONICAL: List[str] = ["journal", "meeting"]

# Aliases that normalize into canonical modes.
_ALIASES: Dict[str, str] = {
    "diary": "journal",
}

# Mode defaults (v1).
# speakers:
# - int: explicit speaker count
# - "auto": let diarization decide (meeting default)
SpeakerDefault = Union[int, str]

_DEFAULT_SPEAKERS: Dict[str, SpeakerDefault] = {
    "journal": 1,
    "meeting": "auto",
}


@dataclass(frozen=True)
class ModeValidation:
    ok: bool
    raw: str
    canonical: Optional[str]
    allowed: List[str]
    message: Optional[str] = None


def allowed_modes() -> List[str]:
    # copy to prevent mutation
    return list(_ALLOWED_CANONICAL)


def normalize_mode(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in _ALIASES:
        return _ALIASES[s]
    return s


def validate_mode(raw: str) -> ModeValidation:
    n = normalize_mode(raw)
    allowed = allowed_modes()

    if n in allowed:
        return ModeValidation(ok=True, raw=raw, canonical=n, allowed=allowed)

    msg = f"Unknown mode '{raw}'. Allowed modes: {', '.join(allowed)}."
    return ModeValidation(ok=False, raw=raw, canonical=None, allowed=allowed, message=msg)


def default_speakers_for_mode(mode: str) -> SpeakerDefault:
    v = validate_mode(mode)
    if not v.ok or v.canonical is None:
        raise ValueError(v.message or "Unknown mode.")
    return _DEFAULT_SPEAKERS[v.canonical]
