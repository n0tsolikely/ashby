from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Dict

from ashby.modules.meetings.schemas.plan import IntentKind


@dataclass(frozen=True)
class ParsedIntent:
    kind: IntentKind
    query: Optional[str] = None
    export_format: Optional[str] = None
    overlay: Optional[Dict[str, str]] = None


def infer_intent(text: str, attachments_present: bool) -> ParsedIntent:
    """
    Deterministic v1 intent inference.
    This is NOT full NLU. It must stay simple, predictable, and testable.
    """
    t = (text or "").strip()
    tl = t.lower()

    # QUEST_007: speaker identity overlay
    # Pattern: "SPEAKER_00 is Greg"
    m = re.match(r"^(speaker_\d{2})\s+is\s+(.+)$", tl, flags=re.IGNORECASE)
    if m:
        label = m.group(1).upper()
        name = t.split("is", 1)[1].strip()
        return ParsedIntent(kind=IntentKind.SPEAKER_MAP_OVERLAY, overlay={label: name})

    # QUEST_007: extract only - "only what Greg said"
    if tl.startswith("only what ") and tl.endswith(" said"):
        who = t[len("only what ") : -len(" said")].strip()
        return ParsedIntent(kind=IntentKind.EXTRACT_ONLY, query=who)

    # QUEST_007: speaker overlay command, e.g. "SPEAKER_00 is Greg"
    m = re.match(r"^(SPEAKER_\d{2})\s+is\s+(.+?)\s*$", t, flags=re.IGNORECASE)
    if m:
        label = m.group(1).upper()
        name = m.group(2).strip()
        if name:
            return ParsedIntent(kind=IntentKind.SPEAKER_MAP_OVERLAY, overlay={label: name})

    # QUEST_007: extract-only command, e.g. "only what Greg said"
    m2 = re.match(r"^only\s+what\s+(.+?)\s+said\s*$", tl)
    if m2:
        who = m2.group(1).strip()
        return ParsedIntent(kind=IntentKind.EXTRACT_ONLY, query=who)

    if tl.startswith("set mode") or tl.startswith("mode "):
        return ParsedIntent(kind=IntentKind.SET_MODE)

    if tl.startswith("set speakers") or tl.startswith("speakers "):
        return ParsedIntent(kind=IntentKind.SET_SPEAKERS)

    if tl.startswith("search") or tl.startswith("find"):
        q = t.split(" ", 1)[1].strip() if " " in t else ""
        return ParsedIntent(kind=IntentKind.SEARCH, query=q)

    if tl.startswith("export"):
        fmt = t.split(" ", 1)[1].strip().lower() if " " in t else None
        return ParsedIntent(kind=IntentKind.EXPORT, export_format=fmt)

    if tl.startswith("formalize") or tl.startswith("run"):
        return ParsedIntent(kind=IntentKind.FORMALIZE)

    if attachments_present:
        return ParsedIntent(kind=IntentKind.INTAKE)

    # default: user talking to Stuart without attachments implies "formalize existing session"
    return ParsedIntent(kind=IntentKind.FORMALIZE)
