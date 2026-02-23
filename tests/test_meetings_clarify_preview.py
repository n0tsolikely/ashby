from ashby.modules.meetings.clarify_or_preview import clarify_or_preview
from ashby.modules.meetings.schemas.clarify import ClarifyField
from ashby.modules.meetings.schemas.run_request import RunRequest


def test_clarify_missing_mode():
    out = clarify_or_preview(text="", run_request=RunRequest())
    assert out.needs_clarification is True
    assert out.clarify is not None
    assert ClarifyField.MODE in out.clarify.fields_needed


def test_mode_provided_defaults_applied():
    out = clarify_or_preview(text="", run_request=RunRequest(mode="meeting"))
    assert out.needs_clarification is False
    assert out.preview is not None
    assert out.preview.mode == "meeting"
    assert "template=default" in out.preview.defaults_used
    assert "retention=MED" in out.preview.defaults_used


def test_invalid_mode_clarifies():
    out = clarify_or_preview(text="", run_request=RunRequest(mode="nope"))
    assert out.needs_clarification is True
    assert out.clarify is not None
    assert ClarifyField.MODE in out.clarify.fields_needed
