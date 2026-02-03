from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ashby.modules.meetings.schemas.clarify import ClarifyOrPreview


class GateStatus(str, Enum):
    UPLOAD_ACCEPTED_NO_PROCESSING = "upload_accepted_no_processing"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_TO_RUN = "ready_to_run"


@dataclass(frozen=True)
class GateDecision:
    status: GateStatus
    message: str
    clarify_or_preview: Optional[ClarifyOrPreview] = None
