"""
Intent schema for Ashby.

All NLU engines (local or GPT) should return dictionaries
created through make_intent() so the router can treat them
all the same way.
"""

from typing import Optional, Dict, Any


def make_intent(
    type: str,
    group: Optional[str] = None,
    brightness: Optional[int] = None,
    delta: Optional[int] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Standardized intent structure used by Ashby.

    Fields:
      - type: one of
          "lights.on"
          "lights.off"
          "lights.adjust"
          "comfort.cold"
          "chat"
          "unknown"
      - group: logical group name, e.g. "captain_america", "thor", "sky"
      - brightness: direct absolute brightness (0–1000) if applicable
      - delta: relative change in brightness (+/-)
      - mode: optional modifier, e.g. "max", "min"
    """
    return {
        "type": type,
        "group": group,
        "brightness": brightness,
        "delta": delta,
        "mode": mode,
    }
