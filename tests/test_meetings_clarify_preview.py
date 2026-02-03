from ashby.modules.meetings.clarify_or_preview import clarify_or_preview
from ashby.modules.meetings.schemas.plan import AttachmentMeta, UIState, SessionContext
from ashby.modules.meetings.schemas.clarify import ClarifyField


def test_mode_missing_triggers_clarification_with_enumerated_options():
    out = clarify_or_preview(text="formalize", ui=UIState(mode=None))
    assert out.needs_clarification is True
    assert out.clarify is not None
    assert ClarifyField.MODE in out.clarify.fields_needed
    # options must include journal + meeting
    opts = out.clarify.options[ClarifyField.MODE]
    values = sorted([o.value for o in opts])
    assert values == ["journal", "meeting"]


def test_defaults_applied_and_disclosed_in_preview():
    out = clarify_or_preview(
        text="formalize",
        ui=UIState(mode="meeting", template=None, speakers=None),
        session=SessionContext(active_session_id="sessx"),
    )
    assert out.needs_clarification is False
    assert out.preview is not None
    assert out.preview.mode == "meeting"
    assert out.preview.template == "default"
    # meeting default speakers is "auto"
    assert out.preview.speakers == "auto"
    assert "template=default" in out.preview.defaults_used
    assert "speakers=auto" in out.preview.defaults_used
    # plan should include a formalize step
    kinds = [s["kind"] for s in out.preview.ordered_steps]
    assert "formalize" in kinds


def test_telegram_door_never_offers_template_selection():
    out = clarify_or_preview(
        text="formalize",
        ui=UIState(mode="journal", template=None, speakers=None),
        door="telegram",
    )
    assert out.needs_clarification is False
    assert out.preview is not None
    assert out.preview.template == "default"
