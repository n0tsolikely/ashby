from __future__ import annotations

import time
from pathlib import Path

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.store import create_session, add_contribution
from ashby.modules.meetings.input_resolver import resolve_input_contribution


def test_resolve_input_contribution_explicit_and_latest(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path))

    session_id = create_session(mode="meeting", title="test")
    lay = init_stuart_root()

    p1 = tmp_path / "a.wav"
    p1.write_bytes(b"one")
    cid1 = add_contribution(session_id=session_id, source_path=p1, source_kind="audio")
    time.sleep(0.01)

    p2 = tmp_path / "b.wav"
    p2.write_bytes(b"two")
    cid2 = add_contribution(session_id=session_id, source_path=p2, source_kind="audio")

    r1 = resolve_input_contribution(session_id=session_id, layout=lay, contribution_id=cid1)
    assert r1.contribution_id == cid1
    assert r1.source_path.exists()

    r2 = resolve_input_contribution(session_id=session_id, layout=lay, contribution_id=None)
    assert r2.contribution_id == cid2
    assert r2.source_path.exists()
