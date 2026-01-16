from __future__ import annotations

import tempfile

import pytest

from ashby.storage.local_fs import LocalFSStorageAdapter


def test_storage_adapter_basic_io_and_overwrite_rules() -> None:
    tmp = tempfile.mkdtemp(prefix="ashby_storage_smoke_")
    s = LocalFSStorageAdapter(tmp)

    # mkdir -p behavior
    s.mkdir("alpha/beta")
    assert s.exists("alpha")
    assert s.exists("alpha/beta")

    # list behavior
    assert "beta" in s.list("alpha")

    # write + read
    s.write_bytes("alpha/beta/file.txt", b"hello", overwrite=False, atomic=True)
    assert s.read_bytes("alpha/beta/file.txt") == b"hello"

    # refuse overwrite by default
    with pytest.raises(FileExistsError):
        s.write_bytes("alpha/beta/file.txt", b"nope", overwrite=False, atomic=True)

    # allow overwrite explicitly
    s.write_bytes("alpha/beta/file.txt", b"ok", overwrite=True, atomic=True)
    assert s.read_bytes("alpha/beta/file.txt") == b"ok"
