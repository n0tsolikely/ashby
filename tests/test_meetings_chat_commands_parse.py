from __future__ import annotations

from ashby.modules.meetings.chat.commands import parse_command


def test_parse_command_basic() -> None:
    cmd = parse_command("/open ses_123")
    assert cmd is not None
    assert cmd.name == "open"
    assert cmd.args == ["ses_123"]


def test_parse_command_non_slash_returns_none() -> None:
    assert parse_command("hello") is None
