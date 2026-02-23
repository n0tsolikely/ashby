from __future__ import annotations

import pytest

from ashby.modules.meetings.schemas.journal_v1 import validate_journal_v1


def test_validate_journal_v1_minimal_ok():
    payload = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "header": {"title": "Test Journal", "mode": "journal", "retention": "MED", "template_id": "default"},
        "narrative_sections": [
            {"section_id": "sec_001", "title": "Entry", "text": "Today was a day."},
        ],
        "action_items": [],
    }
    validate_journal_v1(payload)


def test_validate_journal_v1_key_points_require_citations():
    payload = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "header": {"title": "Test Journal", "mode": "journal", "retention": "MED", "template_id": "default"},
        "narrative_sections": [
            {"section_id": "sec_001", "text": "I went for a walk."},
        ],
        "key_points": [
            {"point_id": "kp_001", "text": "Went for a walk", "citations": []},
        ],
        "action_items": [],
    }
    with pytest.raises(ValueError):
        validate_journal_v1(payload)


def test_validate_journal_v1_action_items_require_citations():
    payload = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "header": {"title": "Test Journal", "mode": "journal", "retention": "MED", "template_id": "default"},
        "narrative_sections": [
            {"section_id": "sec_001", "text": "I should do the thing."},
        ],
        "action_items": [
            {"action_id": "a_001", "text": "Do the thing", "citations": []},
        ],
    }
    with pytest.raises(ValueError):
        validate_journal_v1(payload)


def test_validate_journal_v1_optional_citations_must_be_nonempty_if_present():
    payload = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "header": {"title": "Test Journal", "mode": "journal", "retention": "MED", "template_id": "default"},
        "narrative_sections": [
            {"section_id": "sec_001", "text": "Something happened.", "citations": []},
        ],
        "action_items": [],
    }
    with pytest.raises(ValueError):
        validate_journal_v1(payload)
