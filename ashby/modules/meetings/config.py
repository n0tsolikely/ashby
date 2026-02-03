from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class StuartConfig:
    """
    Canonical config for Stuart (Meetings module).

    STUART_ROOT must be a writable directory outside the repo.
    Default: ~/ashby_runtime/stuart
    Override: environment variable STUART_ROOT
    """
    root: Path

def get_config() -> StuartConfig:
    raw = (os.environ.get("STUART_ROOT") or "").strip()
    if raw:
        root = Path(raw).expanduser().resolve()
    else:
        root = Path("~/ashby_runtime/stuart").expanduser().resolve()
    return StuartConfig(root=root)
