from __future__ import annotations

import pytest

from ashby.core.results import ActionResult, ErrorInfo, err, from_dict, ok_action, ok_artifact


def test_results_roundtrip_and_invariants() -> None:
    a = ok_action("lights.set", target={"group": "kitchen"}, effects={"brightness": 50})
    b = ok_artifact(
        "stuart.transcript",
        artifacts={"transcript": "sessions/s1/transcript.md"},
        metadata={"v": 1},
    )
    c = err("E_TEST", "boom", why="unit")

    for r in (a, b, c):
        d = r.to_dict()
        r2 = from_dict(d)
        assert r2.to_dict() == d

    # ok=True cannot have errors (should fail at construction time)
    with pytest.raises(ValueError):
        ActionResult(
            ok=True,
            errors=[ErrorInfo(code="E_BAD", message="should not exist", detail={})],
            action_type="x",
            target={},
            effects={},
        )

    # invalid artifact path should fail (absolute)
    with pytest.raises(ValueError):
        ok_artifact("t", artifacts={"x": "/abs/path"}, metadata={})
