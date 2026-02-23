from __future__ import annotations

from typing import Any, Dict, List, Optional

from ashby.modules.meetings.schemas.plan import (
    AttachmentMeta,
    MeetingsIntent,
    MeetingsPlan,
    PlanStep,
    PlanStepKind,
    SessionContext,
    UIState,
    ValidationResult,
)


def build_plan(
    intent: MeetingsIntent,
    attachments: Optional[List[AttachmentMeta]],
    ui: UIState,
    session: SessionContext,
    validation: ValidationResult,
) -> MeetingsPlan:
    """
    Build a machine-checkable plan from a resolved intent.
    No execution here. No gating here. That comes in QUEST_017/018.
    """
    attachments = attachments or []

    steps: List[PlanStep] = [PlanStep(kind=PlanStepKind.VALIDATE, params={})]

    def add(kind: PlanStepKind, params: Optional[Dict[str, Any]] = None) -> None:
        steps.append(PlanStep(kind=kind, params=(params or {})))

    k = intent.kind

    if k.value == PlanStepKind.SET_MODE.value:
        add(PlanStepKind.SET_MODE, {"mode": ui.mode})
    elif k.value == PlanStepKind.SET_SPEAKERS.value:
        add(PlanStepKind.SET_SPEAKERS, {"speakers": ui.speakers})
    elif k.value == PlanStepKind.INTAKE.value:
        add(
            PlanStepKind.INTAKE,
            {
                "attachments": [a.__dict__ for a in attachments],
                "session_id": session.active_session_id,
            },
        )
    elif k.value == PlanStepKind.TRANSCRIBE.value:
        params: Dict[str, Any] = {
            "mode": ui.mode,
            "speakers": ui.speakers,
            "session_id": session.active_session_id,
        }
        if isinstance(ui.diarization_enabled, bool):
            params["diarization_enabled"] = ui.diarization_enabled
        add(PlanStepKind.TRANSCRIBE, params)
    elif k.value == PlanStepKind.FORMALIZE.value:
        params: Dict[str, Any] = {
            "mode": ui.mode,
            # Run param contract (QUEST_042): always use template_id + retention.
            "template_id": ui.template or "default",
            "retention": ui.retention or "MED",
            "speakers": ui.speakers,
            "session_id": session.active_session_id,
        }
        if isinstance(ui.diarization_enabled, bool):
            params["diarization_enabled"] = ui.diarization_enabled
        if isinstance(ui.transcript_version_id, str) and ui.transcript_version_id.strip():
            params["transcript_version_id"] = ui.transcript_version_id.strip()
        add(PlanStepKind.FORMALIZE, params)
    elif k.value == PlanStepKind.SEARCH.value:
        # SEARCH can be scoped to an active session and/or a mode (meeting/journal).
        add(
            PlanStepKind.SEARCH,
            {
                "query": intent.query,
                "session_id": session.active_session_id,
                "mode_filter": ui.mode,
            },
        )
    elif k.value == PlanStepKind.EXPORT.value:
        add(PlanStepKind.EXPORT, {"format": intent.export_format, "session_id": session.active_session_id})
    elif k.value == PlanStepKind.SPEAKER_MAP_OVERLAY.value:
        add(
            PlanStepKind.SPEAKER_MAP_OVERLAY,
            {"overlay": intent.overlay or {}, "session_id": session.active_session_id},
        )
    elif k.value == PlanStepKind.EXTRACT_ONLY.value:
        add(
            PlanStepKind.EXTRACT_ONLY,
            {"query": intent.query, "session_id": session.active_session_id},
        )

    return MeetingsPlan(intent=intent, steps=steps, validation=validation)
