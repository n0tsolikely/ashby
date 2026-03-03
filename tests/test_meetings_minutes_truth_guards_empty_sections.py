from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.render.minutes_md import render_minutes_md


def _write_minutes_json_empty_decisions_actions(
    run_dir: Path, *, show_empty_sections: bool = False, include_citations: bool = False
) -> None:
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
        "show_empty_sections": show_empty_sections,
        "include_citations": include_citations,
        "participants": [],
        "topics": [],
        "decisions": [],
        "action_items": [],
        "notes": [],
        "open_questions": [],
    }
    (artifacts / "minutes.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_minutes_md_omits_empty_sections_by_default(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_empty"
    _write_minutes_json_empty_decisions_actions(run_dir)

    render_minutes_md(run_dir)
    txt = (run_dir / "artifacts" / "minutes.md").read_text(encoding="utf-8")

    assert "## Decisions" not in txt
    assert "## Action Items" not in txt
    assert "_No entries._" not in txt


def test_minutes_md_show_empty_sections_true_renders_placeholder(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_empty_show"
    _write_minutes_json_empty_decisions_actions(run_dir, show_empty_sections=True)

    render_minutes_md(run_dir)
    txt = (run_dir / "artifacts" / "minutes.md").read_text(encoding="utf-8")

    assert "## Decisions" in txt
    assert "## Action Items" in txt
    assert "_No entries._" in txt


def test_minutes_md_include_citations_flag_controls_citation_tokens(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_citations_off"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "header": {"title": "Test Minutes", "mode": "meeting", "retention": "MED", "template_id": "default", "created_ts": 123.0},
        "include_citations": False,
        "show_empty_sections": False,
        "participants": [],
        "topics": [],
        "decisions": [{"decision_id": "d1", "text": "Decision text", "citations": [{"segment_id": 0}]}],
        "action_items": [],
        "notes": [],
        "open_questions": [],
    }
    (artifacts / "minutes.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (artifacts / "transcript.json").write_text(
        json.dumps(
            {
                "version": 1,
                "session_id": "ses_test",
                "run_id": run_dir.name,
                "segments": [{"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "x"}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    render_minutes_md(run_dir)
    txt_off = (artifacts / "minutes.md").read_text(encoding="utf-8")
    assert "[S0@" not in txt_off

    run_dir_on = tmp_path / "run_citations_on"
    artifacts_on = run_dir_on / "artifacts"
    artifacts_on.mkdir(parents=True, exist_ok=True)
    payload["run_id"] = run_dir_on.name
    payload["include_citations"] = True
    (artifacts_on / "minutes.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (artifacts_on / "transcript.json").write_text(
        json.dumps(
            {
                "version": 1,
                "session_id": "ses_test",
                "run_id": run_dir_on.name,
                "segments": [{"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "x"}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    render_minutes_md(run_dir_on)
    txt_on = (artifacts_on / "minutes.md").read_text(encoding="utf-8")
    assert "[S0@" in txt_on
