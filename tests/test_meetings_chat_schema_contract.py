from __future__ import annotations

import pytest

from ashby.modules.meetings.schemas.chat import (
    parse_chat_action_v1,
    parse_chat_request_v1,
    parse_chat_response_v1,
)


def test_chat_request_roundtrip_and_unknown_rejected() -> None:
    req = parse_chat_request_v1(
        {
            "session_id": "ses_123",
            "text": "what did we decide?",
            "attachments": [{"filename": "note.txt"}],
            "history_tail": [{"role": "user", "text": "prev"}],
            "ui": {"scope": "session"},
            "client": {"platform": "web"},
        }
    )
    out = req.to_dict()
    assert out["session_id"] == "ses_123"
    assert out["text"] == "what did we decide?"
    assert isinstance(out["attachments"], list)
    assert isinstance(out["history_tail"], list)

    with pytest.raises(ValueError):
        parse_chat_request_v1({"text": "x", "extra_field": True})


def test_chat_response_assistant_roundtrip() -> None:
    payload = {
        "session_id": "ses_123",
        "scope": "session",
        "reply": {
            "kind": "assistant",
            "text": "We decided to ship Friday.",
            "citations": [
                {
                    "session_id": "ses_123",
                    "run_id": "run_123",
                    "segment_id": 7,
                    "speaker_label": "SPEAKER_00",
                    "t_start": 10.0,
                    "t_end": 12.0,
                    "source_path": "runs/run_123/artifacts/transcript.json",
                }
            ],
            "hits": [
                {
                    "session_id": "ses_123",
                    "run_id": "run_123",
                    "snippet": "ship Friday",
                    "score": 0.12,
                    "match_kind": "TITLE_MATCH",
                    "citation": {
                        "session_id": "ses_123",
                        "run_id": "run_123",
                        "segment_id": 7,
                        "speaker_label": "SPEAKER_00",
                    },
                }
            ],
            "actions": [
                {"kind": "open_session", "session_id": "ses_123"},
                {
                    "kind": "jump_to_segment",
                    "session_id": "ses_123",
                    "transcript_version_id": "trv_123",
                    "segment_id": 7,
                },
            ],
        },
    }

    resp = parse_chat_response_v1(payload)
    out = resp.to_dict()
    assert out["scope"] == "session"
    assert out["reply"]["kind"] == "assistant"
    assert len(out["reply"]["citations"]) == 1
    assert len(out["reply"]["hits"]) == 1
    assert len(out["reply"]["actions"]) == 2


def test_chat_reply_contract_for_clarify_and_planner() -> None:
    clarify = parse_chat_response_v1(
        {
            "scope": "session",
            "reply": {
                "kind": "clarify",
                "text": "Choose mode.",
                "clarify": {"fields_needed": ["mode"]},
            },
        }
    )
    assert clarify.reply.kind == "clarify"
    assert isinstance(clarify.reply.clarify, dict)

    planner = parse_chat_response_v1(
        {
            "scope": "session",
            "reply": {
                "kind": "planner",
                "text": "Planned action.",
                "planner": {"steps": [{"kind": "formalize"}]},
            },
        }
    )
    assert planner.reply.kind == "planner"
    assert isinstance(planner.reply.planner, dict)


def test_chat_action_contract_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        parse_chat_action_v1({"kind": "delete_everything", "session_id": "ses_123"})
