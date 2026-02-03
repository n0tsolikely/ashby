from __future__ import annotations

import os
import time

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

def _enc32(n: int, length: int) -> str:
    out = []
    for _ in range(length):
        n, r = divmod(n, 32)
        out.append(_CROCKFORD32[r])
    return "".join(reversed(out))

def new_id(prefix: str) -> str:
    """
    Generate a stable, sortable-ish ID.

    Output shape: {prefix}_{time32}{rand32}
    Example: ses_01JABC...  (prefix is short: ses|con|run|ovr|exp)

    Notes:
    - No external ULID dependency in Option A.
    - This is intentionally swappable later without changing call sites.
    """
    ms = int(time.time() * 1000)
    t = _enc32(ms, 10)  # time component
    r = int.from_bytes(os.urandom(10), "big")  # random component
    rr = _enc32(r, 16)
    return f"{prefix}_{t}{rr}"
