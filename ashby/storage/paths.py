from __future__ import annotations

import re
from pathlib import Path

from ashby.interfaces.storage import validate_rel_path


_SLUG_WS = re.compile(r"\s+")
_SLUG_BAD = re.compile(r"[^A-Za-z0-9_-]+")


def sanitize_slug(name: str, *, max_len: int = 48) -> str:
    """
    Deterministic slug sanitizer.

    Rules (Batch 0 contract):
    - trim
    - spaces -> underscores
    - remove characters outside [A-Za-z0-9_-]
    - enforce max_len (default 48)
    """
    if not isinstance(name, str):
        raise TypeError("name must be a str")
    if not isinstance(max_len, int) or max_len <= 0:
        raise ValueError("max_len must be a positive int")

    s = name.strip()
    s = _SLUG_WS.sub("_", s)
    s = _SLUG_BAD.sub("", s)

    # collapse repeats + trim separators
    s = re.sub(r"_+", "_", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("_-")

    if s == "":
        s = "untitled"

    if len(s) > max_len:
        s = s[:max_len].rstrip("_-")
        if s == "":
            s = "untitled"

    return s


def safe_relpath(*parts: str) -> str:
    """
    Join path parts into a safe relative path suitable for StorageAdapter.

    Rules (Batch 0 contract):
    - join parts with "/"
    - normalize redundant slashes + "." segments
    - forbid absolute parts
    - forbid ".." traversal
    """
    if len(parts) == 0:
        return ""

    for p in parts:
        if not isinstance(p, str):
            raise TypeError("all parts must be str")

    joined = "/".join([p for p in parts if p != ""])
    return validate_rel_path(joined, allow_empty=True)


def ensure_dir(path: Path) -> Path:
    """
    Ensure a directory exists and return it.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def storage_root(base_dir: Path) -> Path:
    """
    Returns the root directory for Ashby storage artifacts.

    This is intentionally separate from memory/ and runtime/.
    """
    return ensure_dir(base_dir)


def profiles_dir(root: Path) -> Path:
    """
    Where profile + consent artifacts live.
    """
    return ensure_dir(root / "profiles")


def sessions_dir(root: Path) -> Path:
    """
    Where session transcripts / meeting artifacts live.
    """
    return ensure_dir(root / "sessions")


def results_dir(root: Path) -> Path:
    """
    Where result objects are persisted.
    """
    return ensure_dir(root / "results")
