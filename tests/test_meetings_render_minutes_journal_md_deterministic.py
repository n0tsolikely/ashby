from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashby.modules.meetings.render.minutes_md import render_minutes_md
from ashby.modules.meetings.render.journal_md import render_journal_md


def _write_transcript_json(run_dir: Path, *, session_id: str) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": session_id,
        "run_id": run_dir.name,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "a"},
            {"segment_id": 1, "start_ms": 1000, "end_ms": 2000, "speaker": "SPEAKER_01", "text": "b"},
            {"segment_id": 2, "start_ms": 2000, "end_ms": 3000, "speaker": "SPEAKER_01", "text": "c"},
        ],
    }
    (artifacts / "transcript.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_minutes_json(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "header": {"title": "Test Minutes", "mode": "meeting", "retention": "MED", "template_id": "default", "created_ts": 123.0},
        "participants": [{"speaker_label": "SPEAKER_01"}, {"speaker_label": "SPEAKER_00"}],
        "topics": [
            {"topic_id": "topic_002", "title": "Second", "summary": "B", "citations": [{"segment_id": 2}, {"segment_id": 1}]},
            {"topic_id": "topic_001", "title": "First", "summary": "A", "citations": [{"segment_id": 0}]},
        ],
        "decisions": [
            {"decision_id": "dec_002", "text": "Do later", "citations": [{"segment_id": 2}]},
            {"decision_id": "dec_001", "text": "Do now", "citations": [{"segment_id": 0}, {"segment_id": 1}]},
        ],
        "action_items": [
            {"action_id": "act_002", "text": "Second action", "assignee": "SPEAKER_01", "due_date": "2026-02-10", "citations": [{"segment_id": 2}]},
            {"action_id": "act_001", "text": "First action", "assignee": None, "due_date": None, "citations": [{"segment_id": 0}]},
        ],
        "notes": [
            {"note_id": "note_0002", "text": "Note two", "citations": [{"segment_id": 2}]},
            {"note_id": "note_0001", "text": "Note one", "citations": [{"segment_id": 0}]},
        ],
        "open_questions": [
            {"question_id": "q_002", "text": "Question two?", "citations": [{"segment_id": 2}]},
            {"question_id": "q_001", "text": "Question one?", "citations": [{"segment_id": 0}]},
        ],
    }
    (artifacts / "minutes.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Needed for stable timestamp rendering in citation tokens.
    _write_transcript_json(run_dir, session_id="ses_test")


def _write_journal_json(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "header": {"title": "Test Journal", "mode": "journal", "retention": "LOW", "template_id": "default", "created_ts": 123.0},
        "mood": "ok",
        "narrative_sections": [
            {"section_id": "sec_002", "title": "Second", "text": "B", "citations": [{"segment_id": 1}]},
            {"section_id": "sec_001", "title": "First", "text": "A", "citations": [{"segment_id": 0}]},
        ],
        "key_points": [
            {"point_id": "kp_002", "text": "Point B", "citations": [{"segment_id": 1}]},
            {"point_id": "kp_001", "text": "Point A", "citations": [{"segment_id": 0}]},
        ],
        "feelings": [
            {"text": "tired", "citations": [{"segment_id": 0}]},
        ],
        "action_items": [
            {"action_id": "ja_002", "text": "Second thing", "assignee": None, "due_date": None, "citations": [{"segment_id": 1}]},
            {"action_id": "ja_001", "text": "First thing", "assignee": "SPEAKER_00", "due_date": "2026-02-11", "citations": [{"segment_id": 0}]},
        ],
    }
    (artifacts / "journal.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Needed for stable timestamp rendering in citation tokens.
    _write_transcript_json(run_dir, session_id="ses_test")


def test_render_minutes_md_deterministic_and_no_overwrite(tmp_path: Path):
    run_dir = tmp_path / "run_minutes"
    _write_minutes_json(run_dir)

    art = render_minutes_md(run_dir)
    out_path = run_dir / "artifacts" / "minutes.md"
    assert out_path.exists()
    txt1 = out_path.read_text(encoding="utf-8")

    # deterministic: delete output and re-render -> identical
    out_path.unlink()
    render_minutes_md(run_dir)
    txt2 = out_path.read_text(encoding="utf-8")
    assert txt1 == txt2

    # citations visible (segment_id + timestamps)
    assert "[S0@00:00:00–00:00:01]" in txt1
    assert "## Decisions" in txt1
    assert "## Action Items" in txt1

    # sorted ordering (dec_001 before dec_002)
    assert txt1.find("(dec_001)") < txt1.find("(dec_002)")

    # no-overwrite enforced
    with pytest.raises(FileExistsError):
        render_minutes_md(run_dir)


def test_render_journal_md_deterministic_and_no_overwrite(tmp_path: Path):
    run_dir = tmp_path / "run_journal"
    _write_journal_json(run_dir)

    art = render_journal_md(run_dir)
    out_path = run_dir / "artifacts" / "journal.md"
    assert out_path.exists()
    txt1 = out_path.read_text(encoding="utf-8")

    # deterministic: delete output and re-render -> identical
    out_path.unlink()
    render_journal_md(run_dir)
    txt2 = out_path.read_text(encoding="utf-8")
    assert txt1 == txt2

    # citations visible for action items + key points
    assert "## Action Items" in txt1
    assert "## Key Points" in txt1
    assert "[S0@00:00:00–00:00:01]" in txt1

    # sorted ordering (ja_001 before ja_002)
    assert txt1.find("(ja_001)") < txt1.find("(ja_002)")

    # no-overwrite enforced
    with pytest.raises(FileExistsError):
        render_journal_md(run_dir)
