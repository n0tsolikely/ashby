from __future__ import annotations

import pytest

from ashby.modules.meetings.schemas.minutes_v1 import validate_minutes_v1


def test_validate_minutes_v1_minimal_ok():
    payload = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "header": {"title": "Test Meeting", "mode": "meeting", "retention": "MED", "template_id": "default"},
        "participants": [{"speaker_label": "SPEAKER_00"}],
        "topics": [{"topic_id": "topic_001", "title": "Intro", "citations": [{"segment_id": 0}]}],
        "decisions": [],
        "action_items": [],
        "notes": [],
        "open_questions": [],
    }
    validate_minutes_v1(payload)


def test_validate_minutes_v1_requires_nonempty_citations():
    payload = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "header": {"title": "Test Meeting", "mode": "meeting", "retention": "MED", "template_id": "default"},
        "participants": [{"speaker_label": "SPEAKER_00"}],
        "topics": [{"topic_id": "topic_001", "title": "Intro", "citations": []}],
        "decisions": [],
        "action_items": [],
        "notes": [],
        "open_questions": [],
    }
    with pytest.raises(ValueError):
        validate_minutes_v1(payload)


def test_validate_minutes_v1_requires_nonempty_citations_for_decisions():
    payload = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "header": {"title": "Test Meeting", "mode": "meeting", "retention": "MED", "template_id": "default"},
        "participants": [{"speaker_label": "SPEAKER_00"}],
        "topics": [{"topic_id": "topic_001", "title": "Intro", "citations": [{"segment_id": 0}]}],
        "decisions": [{"decision_id": "dec_001", "text": "Do X", "citations": []}],
        "action_items": [],
        "notes": [],
        "open_questions": [],
    }
    with pytest.raises(ValueError):
        validate_minutes_v1(payload)


def test_validate_minutes_v1_requires_nonempty_citations_for_action_items():
    payload = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "header": {"title": "Test Meeting", "mode": "meeting", "retention": "MED", "template_id": "default"},
        "participants": [{"speaker_label": "SPEAKER_00"}],
        "topics": [{"topic_id": "topic_001", "title": "Intro", "citations": [{"segment_id": 0}]}],
        "decisions": [],
        "action_items": [{"action_id": "act_001", "text": "Do Y", "assignee": None, "due_date": None, "citations": []}],
        "notes": [],
        "open_questions": [],
    }
    with pytest.raises(ValueError):
        validate_minutes_v1(payload)
