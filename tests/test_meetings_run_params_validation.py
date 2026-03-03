from __future__ import annotations

from pathlib import Path

import pytest

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.store import create_run, create_session, get_run_state


def _runs_snapshot(root: Path) -> list[str]:
    lay = init_stuart_root()
    if not lay.runs.exists():
        return []
    return sorted([p.name for p in lay.runs.iterdir() if p.is_dir()])


def test_create_run_normalizes_template_to_template_id_and_sets_default_retention(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    ses = create_session(mode="meeting", title="t")

    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template": "default"}}]},
    )

    st = get_run_state(run_id)
    step = next(s for s in (st.get("plan") or {}).get("steps") or [] if (s.get("kind") == "formalize"))
    params = step.get("params") or {}

    assert params["template_id"] == "default"
    assert params["retention"] == "MED"
    assert params["include_citations"] is False
    assert params["show_empty_sections"] is False
    assert "template" not in params


def test_create_run_rejects_invalid_retention_before_allocating_run_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    ses = create_session(mode="meeting", title="t")

    before = _runs_snapshot(tmp_path)

    with pytest.raises(ValueError):
        create_run(
            session_id=ses,
            plan={
                "steps": [
                    {"kind": "formalize", "params": {"mode": "meeting", "template_id": "default", "retention": "NOPE"}}
                ]
            },
        )

    after = _runs_snapshot(tmp_path)
    assert after == before


def test_create_run_rejects_invalid_template_before_allocating_run_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    ses = create_session(mode="meeting", title="t")

    before = _runs_snapshot(tmp_path)

    with pytest.raises(ValueError):
        create_run(
            session_id=ses,
            plan={
                "steps": [
                    {
                        "kind": "formalize",
                        "params": {"mode": "meeting", "template_id": "not_a_real_template", "retention": "MED"},
                    }
                ]
            },
        )

    after = _runs_snapshot(tmp_path)
    assert after == before
