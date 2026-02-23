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
from ashby.modules.meetings.schemas.run_request import RunRequest


@dataclass(frozen=True)
class RouterOutput:
    intent: MeetingsIntent
    plan: MeetingsPlan


def build_intent_and_plan(
    text: str = "",
    attachments: Optional[List[AttachmentMeta]] = None,
    run_request: Optional[RunRequest] = None,
    # legacy/back-compat: older call sites may still pass UIState; prefer RunRequest
    ui: Optional[UIState] = None,
    session: Optional[SessionContext] = None,
) -> RouterOutput:
    """Build intent + plan from a normalized, door-facing RunRequest.

    Doors must produce a RunRequest (canonical field names) before asking the router
    to produce a deterministic plan.

    Notes:
    - `ui` is supported as a legacy convenience (converted to RunRequest).
    """

    attachments = attachments or []

    if run_request is None:
        # Legacy/back-compat: allow UIState input, but normalize immediately.
        ui = ui or UIState()
        run_request = RunRequest.from_ui_state(ui)

    # Convert RunRequest -> internal UIState (legacy field name 'template').
    ui_eff = run_request.to_ui_state()
    session = session or SessionContext()

    validation = validate_ui(ui_eff)
    parsed = infer_intent(text=text, attachments_present=(len(attachments) > 0))

    intent = MeetingsIntent(
        kind=parsed.kind,
        raw_text=text or "",
        mode=ui_eff.mode,
        template=ui_eff.template,
        retention=ui_eff.retention,
        speakers=ui_eff.speakers,
        query=parsed.query,
        export_format=parsed.export_format,
        overlay=parsed.overlay,
    )

    plan = build_plan(
        intent=intent,
        attachments=attachments,
        ui=ui_eff,
        session=session,
        validation=validation,
    )

    return RouterOutput(intent=intent, plan=plan)
