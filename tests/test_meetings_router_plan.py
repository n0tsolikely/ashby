from ashby.modules.meetings.router.router import build_intent_and_plan
from ashby.modules.meetings.router.validate import validate_ui
from ashby.modules.meetings.schemas.plan import AttachmentMeta, SessionContext, IntentKind, PlanStepKind, UIState
from ashby.modules.meetings.schemas.run_request import RunRequest


def test_set_mode_plan_step():
    out = build_intent_and_plan(
        text="set mode",
        run_request=RunRequest(mode="journal"),
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
        run_request=RunRequest(mode="meeting"),
        session=SessionContext(active_session_id="sess2"),
    )
    assert out.intent.kind == IntentKind.INTAKE
    assert out.plan.steps[0].kind == PlanStepKind.VALIDATE
    assert out.plan.steps[1].kind == PlanStepKind.INTAKE
    assert out.plan.steps[1].params["session_id"] == "sess2"
    assert len(out.plan.steps[1].params["attachments"]) == 1


def test_formalize_plan_only_no_execution():
    out = build_intent_and_plan(
        text="formalize",
        run_request=RunRequest(mode="meeting", template_id="default", speakers="auto", diarization_enabled=False),
        session=SessionContext(active_session_id="sess3"),
    )
    assert out.intent.kind == IntentKind.FORMALIZE
    assert out.plan.steps[0].kind == PlanStepKind.VALIDATE
    assert out.plan.steps[1].kind == PlanStepKind.FORMALIZE
    assert out.plan.steps[1].params["mode"] == "meeting"
    assert out.plan.steps[1].params["template_id"] == "default"
    assert out.plan.steps[1].params["retention"] == "MED"
    assert out.plan.steps[1].params["diarization_enabled"] is False


def test_search_plan_only():
    out = build_intent_and_plan(
        text="search project aurora",
        run_request=RunRequest(mode="meeting"),
        session=SessionContext(active_session_id="sess4"),
    )
    assert out.intent.kind == IntentKind.SEARCH
    assert out.plan.steps[0].kind == PlanStepKind.VALIDATE
    assert out.plan.steps[1].kind == PlanStepKind.SEARCH
    assert out.plan.steps[1].params["query"] == "project aurora"


def test_formalize_plan_includes_transcript_version_id_when_supplied():
    out = build_intent_and_plan(
        text="formalize",
        run_request=RunRequest(
            mode="meeting",
            template_id="default",
            retention="MED",
            transcript_version_id="trv_abc123",
        ),
        session=SessionContext(active_session_id="sess5"),
    )
    assert out.intent.kind == IntentKind.FORMALIZE
    assert out.plan.steps[1].kind == PlanStepKind.FORMALIZE
    assert out.plan.steps[1].params["transcript_version_id"] == "trv_abc123"


def test_ui_validation_rejects_blank_transcript_version_id_when_provided():
    vr = validate_ui(UIState(mode="meeting", transcript_version_id="   "))
    assert vr.ok is False
    assert any(i.code == "invalid_transcript_version_id" for i in vr.issues)


def test_run_request_round_trips_transcript_version_id():
    rr = RunRequest.from_dict(
        {
            "mode": "meeting",
            "template_id": "default",
            "retention": "med",
            "transcript_version_id": "trv_roundtrip_1",
        }
    )
    ui = rr.to_ui_state()
    assert ui.transcript_version_id == "trv_roundtrip_1"

    rr2 = RunRequest.from_ui_state(ui)
    assert rr2.transcript_version_id == "trv_roundtrip_1"


def test_run_request_round_trips_diarization_enabled_and_legacy_alias():
    rr = RunRequest.from_dict(
        {
            "mode": "meeting",
            "template_id": "default",
            "retention": "med",
            "diarize": False,
        }
    )
    assert rr.diarization_enabled is False
    ui = rr.to_ui_state()
    assert ui.diarization_enabled is False
    rr2 = RunRequest.from_ui_state(ui)
    assert rr2.diarization_enabled is False
