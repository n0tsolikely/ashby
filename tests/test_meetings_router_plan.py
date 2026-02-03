from ashby.modules.meetings.router.router import build_intent_and_plan
from ashby.modules.meetings.schemas.plan import AttachmentMeta, UIState, SessionContext, IntentKind, PlanStepKind


def test_set_mode_plan_step():
    out = build_intent_and_plan(
        text="set mode",
        ui=UIState(mode="journal"),
        session=SessionContext(active_session_id="sess1"),
    )
    assert out.intent.kind == IntentKind.SET_MODE
    assert out.plan.steps[0].kind == PlanStepKind.VALIDATE
    assert out.plan.steps[1].kind == PlanStepKind.SET_MODE
    assert out.plan.steps[1].params["mode"] == "journal"


def test_intake_when_attachments_present():
    out = build_intent_and_plan(
        text="",
        attachments=[AttachmentMeta(filename="audio.wav", mime_type="audio/wav", size_bytes=123)],
        ui=UIState(mode="meeting"),
        session=SessionContext(active_session_id="sess2"),
    )
    assert out.intent.kind == IntentKind.INTAKE
    assert out.plan.steps[1].kind == PlanStepKind.INTAKE
    assert out.plan.steps[1].params["session_id"] == "sess2"
    assert len(out.plan.steps[1].params["attachments"]) == 1


def test_formalize_plan_only_no_execution():
    out = build_intent_and_plan(
        text="formalize",
        ui=UIState(mode="meeting", template="default", speakers="auto"),
        session=SessionContext(active_session_id="sess3"),
    )
    assert out.intent.kind == IntentKind.FORMALIZE
    assert out.plan.steps[1].kind == PlanStepKind.FORMALIZE
    assert out.plan.steps[1].params["mode"] == "meeting"
    assert out.plan.steps[1].params["template"] == "default"


def test_search_plan_only():
    out = build_intent_and_plan(
        text="search project aurora",
        ui=UIState(mode="meeting"),
        session=SessionContext(active_session_id="sess4"),
    )
    assert out.intent.kind == IntentKind.SEARCH
    assert out.plan.steps[1].kind == PlanStepKind.SEARCH
    assert out.plan.steps[1].params["query"] == "project aurora"
