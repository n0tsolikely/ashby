from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.render.minutes_md import render_minutes_md


def _write_minutes_json_empty_decisions_actions(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "header": {
            "title": "Test Minutes",
            "mode": "meeting",
            "retention": "MED",
            "template_id": "default",
            "created_ts": 123.0,
        },
        "participants": [],
        "topics": [],
        "decisions": [],
        "action_items": [],
        "notes": [],
        "open_questions": [],
    }
    (artifacts / "minutes.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_minutes_md_explicitly_states_when_no_decisions_or_actions(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_empty"
    _write_minutes_json_empty_decisions_actions(run_dir)

    render_minutes_md(run_dir)
    txt = (run_dir / "artifacts" / "minutes.md").read_text(encoding="utf-8")

    assert "No explicit decisions recorded." in txt
    assert "No action items recorded." in txt
