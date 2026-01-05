# ashby/capabilities/comfort/handler.py
"""
Comfort capability handler.

Structural Raid rule:
- Router stays thin.
- No behavior change.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ashby.brain.sessions import comfort
from ashby.brain.memory import memory


def handle_comfort_intent(
    *,
    brain: Any,
    user_id: str,
    text_stripped: str,
    intent: Dict[str, Any],
    recent_action_setter: Any,
) -> Optional[str]:
    """
    Returns:
      - str reply if handled
      - None if not handled
    """

    user_id = str(user_id)

    # ------------------------------------------------------------
    # 1) Active HEAT session followups (yes/no/more/etc.)
    # ------------------------------------------------------------
    if comfort.has_active_session(user_id):
        temp, msg = comfort.process_reply(user_id, text_stripped)

        if temp is not None:
            # Persist preference
            try:
                memory.set(user_id, "preferred_temp", float(temp))
            except Exception:
                pass

            # Keep recent action log consistent with the router pipeline
            try:
                recent_action_setter(user_id, "heat", target_temp=float(temp))
            except Exception:
                pass

        return msg

    itype = intent.get("type", "unknown")

    # ------------------------------------------------------------
    # 2) Comfort trigger (“I’m cold”)
    # ------------------------------------------------------------
    if itype == "comfort.cold":
        current_temp = memory.get(user_id, "last_known_temp", 19.0)
        preferred_temp = memory.get(user_id, "preferred_temp", 21.0)

        if current_temp < preferred_temp - 0.5:
            comfort.start_cold_session(user_id, current_temp, preferred_temp)
            return (
                f"It’s {current_temp}°C in here, and you usually like it around "
                f"{preferred_temp}°C. Want me to warm it up?"
            )

        return "It’s a little cool, but still close to what you usually like."

    return None
