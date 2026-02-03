from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class StuartLayout:
    root: Path
    sessions: Path
    contributions: Path
    runs: Path
    overlays: Path
    exports: Path

def layout_for(root: Path) -> StuartLayout:
    root = Path(root)
    return StuartLayout(
        root=root,
        sessions=root / "sessions",
        contributions=root / "contributions",
        runs=root / "runs",
        overlays=root / "overlays",
        exports=root / "exports",
    )

def ensure_layout(layout: StuartLayout) -> None:
    # Create directories if missing. Never delete. Never migrate here.
    layout.root.mkdir(parents=True, exist_ok=True)
    layout.sessions.mkdir(parents=True, exist_ok=True)
    layout.contributions.mkdir(parents=True, exist_ok=True)
    layout.runs.mkdir(parents=True, exist_ok=True)
    layout.overlays.mkdir(parents=True, exist_ok=True)
    layout.exports.mkdir(parents=True, exist_ok=True)
