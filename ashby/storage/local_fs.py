from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ashby.interfaces.storage import StorageAdapterMixin, validate_rel_path


class LocalFSStorageAdapter(StorageAdapterMixin):
    """
    Local filesystem implementation of the StorageAdapter contract.

    - Rooted namespace (all operations occur under root_dir)
    - Path traversal blocked (delegates to validate_rel_path)
    - No silent overwrite (overwrite=False by default)
    - Atomic writes (temp file in same directory + fsync + os.replace)
    """

    def __init__(self, root_dir: str):
        if not isinstance(root_dir, str):
            raise TypeError("root_dir must be a str")

        root_dir = root_dir.strip()
        if root_dir == "":
            raise ValueError("root_dir must not be empty")

        root = Path(root_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

        self._root: Path = root

    def root(self) -> str:
        return str(self._root)

    def _abs_path(self, rel_path: str, *, allow_empty: bool = False) -> Path:
        rel = validate_rel_path(rel_path, allow_empty=allow_empty)
        if rel == "":
            return self._root

        p = self._root / rel

        # Defensive: prevent escapes via symlinks in existing path segments.
        # (validate_rel_path already blocks ".." segments and absolute paths.)
        resolved_root = self._root.resolve()
        resolved_target = p.resolve(strict=False)

        if hasattr(resolved_target, "is_relative_to"):
            if not resolved_target.is_relative_to(resolved_root):
                raise ValueError("rel_path escapes storage root")
        else:
            common = os.path.commonpath([str(resolved_root), str(resolved_target)])
            if common != str(resolved_root):
                raise ValueError("rel_path escapes storage root")

        return p

    @staticmethod
    def _fsync_dir(dir_path: Path) -> None:
        """
        Best-effort directory fsync for rename durability on POSIX.
        No-op on platforms/filesystems where this isn't supported.
        """
        try:
            fd = os.open(str(dir_path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception:
            # Intentionally best-effort. Atomicity is still ensured by os.replace.
            pass

    def exists(self, rel_path: str) -> bool:
        p = self._abs_path(rel_path, allow_empty=True)
        return p.exists()

    def mkdir(self, rel_dir: str) -> None:
        p = self._abs_path(rel_dir, allow_empty=True)
        if p == self._root:
            # mkdir -p on root is a no-op (root ensured in __init__).
            return
        p.mkdir(parents=True, exist_ok=True)

    def list(self, rel_dir: str) -> list[str]:
        p = self._abs_path(rel_dir, allow_empty=True)
        if not p.exists() or not p.is_dir():
            return []
        try:
            return sorted([child.name for child in p.iterdir()])
        except FileNotFoundError:
            return []

    def read_bytes(self, rel_path: str) -> bytes:
        p = self._abs_path(rel_path, allow_empty=False)
        return p.read_bytes()

    def write_bytes(
        self,
        rel_path: str,
        data: bytes,
        *,
        overwrite: bool = False,
        atomic: bool = True,
    ) -> None:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")

        target = self._abs_path(rel_path, allow_empty=False)
        target.parent.mkdir(parents=True, exist_ok=True)

        if not overwrite and target.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {rel_path}")

        if not atomic:
            mode = "wb" if overwrite else "xb"
            with open(target, mode) as f:
                f.write(bytes(data))
                f.flush()
                os.fsync(f.fileno())
            return

        # Atomic path: write temp file in same directory, fsync, then replace.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=".tmp.",
            suffix=".part",
        )
        tmp_path = Path(tmp_name)

        try:
            with os.fdopen(fd, "wb") as f:
                f.write(bytes(data))
                f.flush()
                os.fsync(f.fileno())

            # Re-check overwrite guard to reduce race risk (still best-effort).
            if not overwrite and target.exists():
                raise FileExistsError(f"Refusing to overwrite existing file: {rel_path}")

            os.replace(str(tmp_path), str(target))
            self._fsync_dir(target.parent)

        finally:
            # If os.replace succeeded, tmp_path won't exist anymore.
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
