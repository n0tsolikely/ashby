from __future__ import annotations

from ashby.modules.meetings.chat.commands import handle_command, parse_command


def test_new_template_command_returns_template_draft_action() -> None:
    cmd = parse_command("/new_template meeting | Weekly Minutes | attendees, decisions, action items")
    assert cmd is not None

    reply = handle_command(cmd, ui_state={}, sessions_index=[])
    assert reply.kind == "assistant"
    assert len(reply.actions) == 1
    action = reply.actions[0]
    assert action.kind == "template_draft"
    assert action.mode == "meeting"
    assert action.template_title == "Weekly Minutes"
    assert "##" in action.template_text
    assert action.defaults["include_citations"] is False
    assert action.defaults["show_empty_sections"] is False
