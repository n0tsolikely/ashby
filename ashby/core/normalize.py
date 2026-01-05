from __future__ import annotations
from typing import Optional

def _clamp_level(level: int) -> int:
    return max(0, min(1000, int(level)))

# TEMP / GUILD NOTE:
# Brightness percent normalization (e.g. "60%") currently lives in router
# so percent-based commands map correctly to Ashby’s 0–1000 scale.
# This logic belongs in the NLU / intent normalization layer long-term.
# TODO (future RAID): extract into nlu_manager or brain/normalize.py
# once intent normalization is centralized.


def _normalize_brightness_to_0_1000(text: str, brightness: Optional[int]) -> Optional[int]:
    """
    If user used a percent sign, treat 0–100 as percent and convert to 0–1000 scale.
    Examples:
      "100%" -> 1000
      "60%"  -> 600
      "10%"  -> 100
    If no %, assume brightness already in 0–1000.
    """
    if brightness is None:
        return None

    try:
        b = int(brightness)
    except Exception:
        return None

    if "%" in (text or ""):
        # percent semantics
        b = max(0, min(100, b))
        return b * 10

    # raw 0–1000 semantics
    return b



def _normalize_group_from_free_text(text: str) -> str:
    """
    If user replies with something like "thor bro" after we asked "which lights?",
    normalize into a group key like "thor".
    """
    low = text.lower().strip()

    # strip filler endings
    for filler in ["man", "bro", "dude"]:
        if low.endswith(" " + filler):
            low = low[: -len(filler) - 1].strip()

    # strip leading "the "
    if low.startswith("the "):
        low = low[4:]

    return low.replace(" ", "_")

def _intensity_multiplier(text: str) -> int:
    low = (text or "").lower()

    mult = 1

    # caps = emphasis
    if any(w.isupper() and len(w) >= 3 for w in (text or "").split()):
        mult = max(mult, 2)

    # common emphasis words
    if "way way" in low or "super" in low or "insanely" in low:
        mult = max(mult, 4)
    elif "way" in low or "really" in low or "so " in low:
        mult = max(mult, 3)

    # “too bright / too dark” implies stronger correction than a nudge
    if "too bright" in low or "too dark" in low:
        mult = max(mult, 4)

    return mult

def _is_direct_light_command(text: str) -> bool:
    low = (text or "").strip().lower()

    # “command tone” starters
    command_starts = (
        "turn ", "set ", "make ", "dim ", "brighten ",
        "kill ", "shut ", "lights ", "light ",
    )
    if low.startswith(command_starts):
        return True

    # one-word / short control followups are also “direct”
    direct_tokens = {
        "on", "off", "more", "again", "up", "down",
        "brighter", "darker", "dim", "max",
        "kill it", "shut it",
    }
    if low in direct_tokens:
        return True

    return False


def _reply_style_for_lights(text: str) -> str:
    # direct commands = short
    if _is_direct_light_command(text):
        return "short"
    # vibe statements = chatty
    return "chatty"


