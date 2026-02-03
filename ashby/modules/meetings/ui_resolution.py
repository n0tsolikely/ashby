from __future__ import annotations

import re
from typing import Optional, Union

from ashby.modules.meetings.schemas.plan import UIState


_SPEAKERS_RE = re.compile(r"\b(?:speakers?|spk)\s*[:=]?\s*(auto|\d+)\b", re.IGNORECASE)


def _extract_mode(text: str) -> Optional[str]:
    tl = (text or "").lower()
    if " journal" in f" {tl}" or tl.strip() == "journal":
        return "journal"
    if " meeting" in f" {tl}" or tl.strip() == "meeting":
        return "meeting"
    return None


def _extract_speakers(text: str) -> Optional[Union[int, str]]:
    m = _SPEAKERS_RE.search(text or "")
    if not m:
        return None
    val = m.group(1).strip().lower()
    if val == "auto":
        return "auto"
    try:
        n = int(val)
        return n
    except ValueError:
        return None


def resolve_ui_from_text(text: str, ui: UIState) -> UIState:
    """
    Deterministic v1 resolver: lets message specify mode/speakers without UI state.
    Does not guess template (v1 default is handled elsewhere).
    """
    mode = ui.mode or _extract_mode(text)
    speakers = ui.speakers if ui.speakers is not None else _extract_speakers(text)
    return UIState(mode=mode, template=ui.template, speakers=speakers)
