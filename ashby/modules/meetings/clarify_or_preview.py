from __future__ import annotations

from dataclasses import asdict
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
from ashby.modules.meetings.ui_resolution import resolve_ui_from_text


def clarify_or_preview(
    text: str = "",
    attachments: Optional[List[AttachmentMeta]] = None,
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
    """
    attachments = attachments or []
    ui = ui or UIState()
    ui = resolve_ui_from_text(text=text, ui=ui)
    session = session or SessionContext()

    fields_needed: List[ClarifyField] = []
    options = {}

    # MODE is the only required clarification in v1.
    if ui.mode is None:
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
    mv = validate_mode(ui.mode)
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
    eff_template = ui.template
    eff_speakers = ui.speakers

    if eff_template is None:
        eff_template = "default"
        defaults_used.append("template=default")

    if eff_speakers is None:
        eff_speakers = default_speakers_for_mode(eff_mode)
        defaults_used.append(f"speakers={eff_speakers}")

    # Door constraint: Telegram never offers template selection.
    # (We don't offer it anyway; this is just a disclosure note hook.)
    if door.strip().lower() == "telegram":
        # No extra action needed; keep defaults-only behavior.
        pass

    # Build plan using effective UI selections.
    eff_ui = UIState(mode=eff_mode, template=eff_template, speakers=eff_speakers)
    out = build_intent_and_plan(text=text, attachments=attachments, ui=eff_ui, session=session)

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
