from __future__ import annotations

from ashby.modules.meetings.chat.commands import handle_command, parse_command


def test_sessions_command_returns_open_actions() -> None:
    cmd = parse_command("/sessions")
    assert cmd is not None
    reply = handle_command(
        cmd,
        sessions_index=[
            {"session_id": "ses_1", "title": "Alpha"},
            {"session_id": "ses_2", "title": "Beta"},
        ],
    )
    assert any(a.kind == "open_session" for a in reply.actions)


def test_open_command_ambiguous_returns_clarify() -> None:
    cmd = parse_command("/open weekly")
    assert cmd is not None
    reply = handle_command(
        cmd,
        sessions_index=[
            {"session_id": "ses_a", "title": "Weekly Sync"},
            {"session_id": "ses_b", "title": "Weekly Product Sync"},
        ],
    )
    assert reply.kind == "clarify"
