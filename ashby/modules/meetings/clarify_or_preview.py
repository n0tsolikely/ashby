from __future__ import annotations

from typing import List, Optional

from ashby.modules.meetings.mode_registry import allowed_modes, default_speakers_for_mode, validate_mode
from ashby.modules.meetings.router.router import build_intent_and_plan
from ashby.modules.meetings.schemas.clarify import (
    ClarifyField,
    ClarifyOption,
    ClarifyOrPreview,
    ClarifyPrompt,
    PlanPreview,
)
from ashby.modules.meetings.schemas.plan import AttachmentMeta, SessionContext, UIState
from ashby.modules.meetings.schemas.run_request import RunRequest
from ashby.modules.meetings.ui_resolution import resolve_ui_from_text


def clarify_or_preview(
    text: str = "",
    attachments: Optional[List[AttachmentMeta]] = None,
    run_request: Optional[RunRequest] = None,
    # legacy/back-compat: older call sites may still pass UIState
    ui: Optional[UIState] = None,
    session: Optional[SessionContext] = None,
    door: str = "cli",
) -> ClarifyOrPreview:
    """
    QUEST_017:
    - If mode missing -> ask (enumerated options).
    - If speakers/template missing -> apply defaults + disclose in preview.
    - Telegram: never offer template selection (v1 default only).
    No execution / 'go' gating here (QUEST_018).

    Notes:
    - Doors should pass `run_request` (canonical field names).
    - `ui` is supported as legacy input (converted to RunRequest immediately).
    """

    attachments = attachments or []

    if run_request is None:
        ui = ui or UIState()
        run_request = RunRequest.from_ui_state(ui)

    # Resolve any implicit UI hints from text (e.g. "mode meeting").
    ui0 = run_request.to_ui_state()
    ui0 = resolve_ui_from_text(text=text, ui=ui0)
    session = session or SessionContext()

    fields_needed: List[ClarifyField] = []
    options = {}

    # MODE is the only required clarification in v1.
    if ui0.mode is None:
        fields_needed.append(ClarifyField.MODE)
        options[ClarifyField.MODE] = [ClarifyOption(value=m) for m in allowed_modes()]

        msg = "Choose a mode: journal or meeting."
        return ClarifyOrPreview(
            needs_clarification=True,
            clarify=ClarifyPrompt(
                message=msg,
                fields_needed=fields_needed,
                options=options,
                notes=None,
            ),
            preview=None,
        )

    # Mode provided: validate early; if invalid, clarify again.
    mv = validate_mode(ui0.mode)
    if not mv.ok or mv.canonical is None:
        fields_needed.append(ClarifyField.MODE)
        options[ClarifyField.MODE] = [ClarifyOption(value=m) for m in allowed_modes()]
        return ClarifyOrPreview(
            needs_clarification=True,
            clarify=ClarifyPrompt(
                message=mv.message or "Invalid mode. Choose journal or meeting.",
                fields_needed=fields_needed,
                options=options,
            ),
            preview=None,
        )

    # Apply defaults for preview (disclose).
    defaults_used: List[str] = []

    eff_mode = mv.canonical
    eff_template = ui0.template
    eff_retention = ui0.retention
    eff_speakers = ui0.speakers

    if eff_template is None:
        eff_template = "default"
        defaults_used.append("template=default")

    # QUEST_042: retention becomes a first-class run param (default MED).
    if eff_retention is None:
        eff_retention = "MED"
        defaults_used.append("retention=MED")

    if eff_speakers is None:
        eff_speakers = default_speakers_for_mode(eff_mode)
        defaults_used.append(f"speakers={eff_speakers}")

    # Door constraint: Telegram never offers template selection.
    # (We don't offer it anyway; this is just a disclosure note hook.)
    if door.strip().lower() == "telegram":
        # No extra action needed; keep defaults-only behavior.
        pass

    # Build plan using effective UI selections.
    eff_ui = UIState(mode=eff_mode, template=eff_template, retention=eff_retention, speakers=eff_speakers)
    eff_rr = RunRequest.from_ui_state(eff_ui)
    out = build_intent_and_plan(text=text, attachments=attachments, run_request=eff_rr, session=session)

    # Plan preview is deterministic and renderable.
    preview = PlanPreview(
        mode=eff_mode,
        template=str(eff_template),
        speakers=str(eff_speakers),
        defaults_used=defaults_used,
        ordered_steps=[{"kind": s.kind.value, "params": dict(s.params)} for s in out.plan.steps],
        ambiguities=[],
    )

    return ClarifyOrPreview(needs_clarification=False, clarify=None, preview=preview)
