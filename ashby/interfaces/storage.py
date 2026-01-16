from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable


def validate_rel_path(rel_path: str, *, allow_empty: bool = False) -> str:
    """
    Validate + normalize a relative path for use with StorageAdapter.

    Contract (Batch 0):
    - must NOT start with "/" or "\\"
    - must NOT contain ".." path segments
    - must NOT be empty for read/write paths (allow_empty=False)
    - if violated: raise ValueError

    Normalization:
    - "\\" is treated as a separator (converted to "/") for safety/determinism
    - redundant slashes are collapsed
    - "." segments are removed
    """
    if not isinstance(rel_path, str):
        raise TypeError("rel_path must be a str")

    if rel_path == "":
        if allow_empty:
            return ""
        raise ValueError("rel_path must not be empty")

    rel_path = rel_path.replace("\\", "/")

    if rel_path.startswith("/"):
        raise ValueError("rel_path must be relative (no leading slash)")

    parts: list[str] = []
    for seg in rel_path.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            raise ValueError("path traversal is not allowed ('..')")
        parts.append(seg)

    normalized = "/".join(parts)

    if normalized == "" and not allow_empty:
        raise ValueError("rel_path must not be empty")

    return normalized


@runtime_checkable
class StorageAdapter(Protocol):
    """
    StorageAdapter represents a rooted storage namespace.

    All paths passed to it are relative paths (no leading "/") and must not escape root.
    """

    def root(self) -> str:
        """Returns absolute path of the adapter’s root directory."""
        ...

    def exists(self, rel_path: str) -> bool:
        """True if file or directory exists."""
        ...

    def mkdir(self, rel_dir: str) -> None:
        """Ensures directory exists (mkdir -p behavior)."""
        ...

    def list(self, rel_dir: str) -> list[str]:
        """Lists names (not full paths) within the directory. Returns [] if dir missing."""
        ...

    def read_bytes(self, rel_path: str) -> bytes:
        """Reads file bytes. Must raise FileNotFoundError if missing."""
        ...

    def write_bytes(
        self,
        rel_path: str,
        data: bytes,
        *,
        overwrite: bool = False,
        atomic: bool = True,
    ) -> None:
        """
        Writes bytes to rel_path.

        Rules:
        - default overwrite=False MUST refuse to overwrite existing files
        - atomic=True MUST perform atomic replace semantics:
            write to temp file in same directory -> fsync -> os.replace
        - if overwrite=True, it may replace existing file (still atomic by default)
        """
        ...


class StorageAdapterMixin:
    """Optional convenience helpers implemented in terms of read_bytes/write_bytes."""

    def read_text(self, rel_path: str, encoding: str = "utf-8") -> str:
        data = self.read_bytes(rel_path)  # type: ignore[attr-defined]
        return data.decode(encoding)

    def write_text(
        self,
        rel_path: str,
        text: str,
        *,
        encoding: str = "utf-8",
        overwrite: bool = False,
        atomic: bool = True,
    ) -> None:
        data = text.encode(encoding)
        self.write_bytes(rel_path, data, overwrite=overwrite, atomic=atomic)  # type: ignore[attr-defined]

    def read_json(self, rel_path: str) -> Any:
        return json.loads(self.read_text(rel_path))

    def write_json(
        self,
        rel_path: str,
        obj: Any,
        *,
        overwrite: bool = False,
        atomic: bool = True,
        indent: int = 2,
    ) -> None:
        text = json.dumps(obj, indent=indent, ensure_ascii=False) + "\n"
        self.write_text(rel_path, text, overwrite=overwrite, atomic=atomic)
