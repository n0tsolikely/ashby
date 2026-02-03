from __future__ import annotations

from pathlib import Path

from .config import get_config
from .layout import layout_for, ensure_layout, StuartLayout

def init_stuart_root() -> StuartLayout:
    cfg = get_config()
    lay = layout_for(cfg.root)
    ensure_layout(lay)
    return lay

def get_root_path() -> Path:
    return get_config().root
