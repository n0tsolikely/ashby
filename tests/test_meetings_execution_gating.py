from ashby.modules.meetings.execution_gating import decide_execution
from ashby.modules.meetings.schemas.gating import GateStatus
from ashby.modules.meetings.schemas.plan import AttachmentMeta, UIState


def test_upload_never_processes_without_go():
    d = decide_execution(
        text="formalize",
        attachments=[AttachmentMeta(filename="a.wav")],
        ui=UIState(mode="meeting"),
    )
    assert d.status == GateStatus.UPLOAD_ACCEPTED_NO_PROCESSING
    assert "No processing" in d.message


def test_go_without_mode_requires_clarification():
    d = decide_execution(
        text="go formalize",
        attachments=[AttachmentMeta(filename="a.wav")],
        ui=UIState(mode=None),
    )
    assert d.status == GateStatus.NEEDS_CLARIFICATION
    assert d.clarify_or_preview is not None
    assert d.clarify_or_preview.needs_clarification is True


def test_go_with_mode_allows_ready_to_run():
    d = decide_execution(
        text="go formalize",
        attachments=[AttachmentMeta(filename="a.wav")],
        ui=UIState(mode="meeting"),
    )
    assert d.status == GateStatus.READY_TO_RUN
