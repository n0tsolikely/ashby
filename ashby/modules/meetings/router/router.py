from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ashby.modules.meetings.intent_parser import infer_intent
from ashby.modules.meetings.plan_builder import build_plan
from ashby.modules.meetings.router.validate import validate_ui
from ashby.modules.meetings.schemas.plan import (
    AttachmentMeta,
    MeetingsIntent,
    MeetingsPlan,
    SessionContext,
    UIState,
)


@dataclass(frozen=True)
class RouterOutput:
    intent: MeetingsIntent
    plan: MeetingsPlan


def build_intent_and_plan(
    text: str = "",
    attachments: Optional[List[AttachmentMeta]] = None,
    ui: Optional[UIState] = None,
    session: Optional[SessionContext] = None,
) -> RouterOutput:
    attachments = attachments or []
    ui = ui or UIState()
    session = session or SessionContext()

    validation = validate_ui(ui)
    parsed = infer_intent(text=text, attachments_present=(len(attachments) > 0))

    intent = MeetingsIntent(
        kind=parsed.kind,
        raw_text=text or "",
        mode=ui.mode,
        template=ui.template,
        speakers=ui.speakers,
        query=parsed.query,
        export_format=parsed.export_format,
        overlay=parsed.overlay,
    )

    plan = build_plan(
        intent=intent,
        attachments=attachments,
        ui=ui,
        session=session,
        validation=validation,
    )
    return RouterOutput(intent=intent, plan=plan)
