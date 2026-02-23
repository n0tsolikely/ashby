from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.render.minutes_md import render_minutes_md


def test_minutes_md_applies_speaker_map_overlay_to_participants_and_lines(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    # Minimal run.json with an inline overlay mapping snapshot.
    run_state = {
        "run_id": run_dir.name,
        "artifacts": [
            {"kind": "speaker_map_overlay", "mapping": {"SPEAKER_00": "Greg"}}
        ],
    }
    (run_dir / "run.json").write_text(json.dumps(run_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Transcript for citation timestamps.
    transcript = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "hello"},
        ],
    }
    (artifacts / "transcript.json").write_text(json.dumps(transcript, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    minutes = {
        "version": 1,
        "session_id": "ses_test",
        "run_id": run_dir.name,
        "header": {"title": "t", "mode": "meeting", "retention": "MED", "template_id": "default", "created_ts": 1.0},
        "participants": [{"speaker_label": "SPEAKER_00"}],
        "topics": [],
        "decisions": [{"decision_id": "dec_001", "text": "SPEAKER_00: Decide", "citations": [{"segment_id": 0}]}],
        "action_items": [],
        "notes": [{"note_id": "n1", "text": "SPEAKER_00: Note", "citations": [{"segment_id": 0}]}],
        "open_questions": [],
    }
    (artifacts / "minutes.json").write_text(json.dumps(minutes, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    render_minutes_md(run_dir)
    out = (artifacts / "minutes.md").read_text(encoding="utf-8")

    # Participant mapping line
    assert "`SPEAKER_00` \u2192 Greg" in out

    # Overlay applied to speaker-prefixed lines
    assert "Greg: Decide" in out
    assert "Greg: Note" in out
