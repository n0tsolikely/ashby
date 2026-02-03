from ashby.modules.meetings.mode_registry import allowed_modes, validate_mode, default_speakers_for_mode


def test_allowed_modes_are_enumerated():
    assert allowed_modes() == ["journal", "meeting"]


def test_mode_alias_diary_normalizes_to_journal():
    v = validate_mode("diary")
    assert v.ok is True
    assert v.canonical == "journal"


def test_unknown_mode_rejected_with_allowed_list():
    v = validate_mode("podcast")
    assert v.ok is False
    assert v.canonical is None
    assert "Allowed modes" in (v.message or "")
    assert "journal" in (v.message or "")
    assert "meeting" in (v.message or "")


def test_default_speakers():
    assert default_speakers_for_mode("journal") == 1
    assert default_speakers_for_mode("diary") == 1
    assert default_speakers_for_mode("meeting") == "auto"
