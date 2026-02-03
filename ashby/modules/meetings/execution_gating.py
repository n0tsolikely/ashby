from __future__ import annotations

import re
from typing import List, Optional

from ashby.modules.meetings.clarify_or_preview import clarify_or_preview
from ashby.modules.meetings.schemas.gating import GateDecision, GateStatus
from ashby.modules.meetings.schemas.plan import AttachmentMeta, SessionContext, UIState


_GO_RE = re.compile(r"\bgo\b", re.IGNORECASE)


def _has_go_token(text: str) -> bool:
    return bool(_GO_RE.search(text or ""))


def decide_execution(
    text: str = "",
    attachments: Optional[List[AttachmentMeta]] = None,
    ui: Optional[UIState] = None,
    session: Optional[SessionContext] = None,
    door: str = "cli",
    explicit_go: bool = False,
) -> GateDecision:
    """
    QUEST_018:
    - Uploading is never equivalent to processing.
    - Heavy work requires explicit go (text token or button/flag).
    - If plan can't be fully specified, return clarification/preview, not execution.
    """
    attachments = attachments or []
    ui = ui or UIState()
    session = session or SessionContext()

    go = explicit_go or _has_go_token(text)

    cop = clarify_or_preview(
        text=text,
        attachments=attachments,
        ui=ui,
        session=session,
        door=door,
    )

    if cop.needs_clarification:
        return GateDecision(
            status=GateStatus.NEEDS_CLARIFICATION,
            message="Need clarification before anything can run.",
            clarify_or_preview=cop,
        )

    # If there are attachments and no go, we accept upload but do not process.
    if (len(attachments) > 0) and (not go):
        return GateDecision(
            status=GateStatus.UPLOAD_ACCEPTED_NO_PROCESSING,
            message="Upload received. No processing started. Say 'go' to run.",
            clarify_or_preview=cop,
        )

    # If user is asking to run but there's no explicit go, we still do preview-only.
    if not go:
        return GateDecision(
            status=GateStatus.UPLOAD_ACCEPTED_NO_PROCESSING,
            message="Ready to run, but waiting for explicit 'go'.",
            clarify_or_preview=cop,
        )

    return GateDecision(
        status=GateStatus.READY_TO_RUN,
        message="Explicit go received. Ready to run.",
        clarify_or_preview=cop,
    )
