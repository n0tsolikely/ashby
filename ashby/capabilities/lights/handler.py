# ashby/capabilities/lights/handler.py
"""
Lights capability handler.

NOTE (Structural Raid rule):
- This file is created first with the existing router lights logic copied in.
- Router will NOT call this yet (Step 1B will wire it in).
- Zero behavior change in this step.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ashby.control.device_control import set_group_brightness
from ashby.brain.sessions import lighting
from ashby.brain.memory import memory
from ashby.core import normalize
from ashby.core.safe_chat import safe_chat


def handle_lights_intent(
    *,
    brain: Any,
    user_id: str,
    text_stripped: str,
    intent: Dict[str, Any],
    recent_action_getter: Any,
    recent_action_setter: Any,
    inject_state_fn: Any,
) -> Optional[str]:
    """
    Returns:
      - str reply if it handled the intent
      - None if not a lights intent
    """
    itype = intent.get("type", "unknown")
    if not str(itype).startswith("lights."):
        return None

    group = intent.get("group")
    brightness = intent.get("brightness")
    delta = intent.get("delta")
    mode = intent.get("mode")

    low = (text_stripped or "").lower().strip()

    # ------------------------------------------------------------
    # Lights: ON
    # ------------------------------------------------------------
    if itype == "lights.on":
        if not group:
            lighting.set_awaiting_target(user_id, intent)
            return safe_chat(brain, user_id, "Which lights? (Thor, Captain, Sky)")

        b = normalize._normalize_brightness_to_0_1000(text_stripped, brightness)
        level = 600 if b is None else normalize._clamp_level(b)

        set_group_brightness(group, level)

        inject_state_fn(
            brain,
            f"I turned on {group.replace('_', ' ')} lights to {round(level / 10)} percent."
        )

        lighting.start_session(user_id, group, level, step=100)
        recent_action_setter(user_id, "lighting", group=group, level=level, verb="on")

        nice_name = group.replace("_", " ")
        style = normalize._reply_style_for_lights(text_stripped)

        if style == "short":
            if mode == "max":
                return safe_chat(brain, user_id, f"Done. {nice_name} maxed.")
            return safe_chat(brain, user_id, f"Done. {nice_name} on.")
        else:
            if mode == "max":
                return safe_chat(
                    brain, user_id,
                    f"Cranking {nice_name} to max. You trying to light up the whole damn place?"
                )
            return safe_chat(brain, user_id, f"Alright—{nice_name} is on. How’s that feel?")

    # ------------------------------------------------------------
    # Lights: OFF
    # ------------------------------------------------------------
    if itype == "lights.off":
        sess = lighting.get_session(user_id)
        target_group = group or (sess.get("group") if sess else None)

        if not target_group:
            return safe_chat(brain, user_id, text_stripped)

        set_group_brightness(target_group, 0)
        lighting.end_session(user_id)
        recent_action_setter(user_id, "lighting", group=target_group, level=0, verb="off")

        nice_name = target_group.replace("_", " ")
        style = normalize._reply_style_for_lights(text_stripped)

        if style == "short":
            return safe_chat(brain, user_id, f"Done. {nice_name} off.")
        return safe_chat(brain, user_id, f"Alright—{nice_name} is off. Peace and darkness 😈")

    # ------------------------------------------------------------
    # Lights: ADJUST
    # ------------------------------------------------------------
    if itype == "lights.adjust":
        sess = lighting.get_session(user_id)
        target_group = group or (sess.get("group") if sess else None)

        if not target_group:
            return safe_chat(brain, user_id, text_stripped)

        # If we have an active session, use it; else start at 600
        if sess and sess.get("group") == target_group:
            current_level = int(sess.get("level", 600))
            last_delta = int(sess.get("last_delta", 0))
            step = int(sess.get("step", 100))
        else:
            current_level = 600
            last_delta = 0
            step = 100

        # Generic followups -> reuse last delta ONLY if user didn't specify direction
        explicit_down = ("down" in low) or ("less" in low) or ("dimmer" in low) or ("darker" in low) or ("too bright" in low) or ("way too bright" in low)
        explicit_up   = ("up" in low) or ("brighter" in low) or ("too dark" in low) or ("way too dark" in low)

        generic_followups = {"more", "again", "keep going", "little more", "bit more", "a bit more"}

        if (low in generic_followups) and (not explicit_down) and (not explicit_up):
            if last_delta != 0:
                delta = last_delta

        # Absolute level
        if brightness is not None:
            b = normalize._normalize_brightness_to_0_1000(text_stripped, brightness)
            new_level = normalize._clamp_level(b if b is not None else brightness)
            last_delta = 0
        else:
            # Delta-based
            if delta is None and last_delta != 0:
                delta = last_delta

            if delta is None:
                # Try the session parser for words like darker/brighter/back one/kill it
                g, lvl, msg = lighting.process_adjust_phrase(user_id, text_stripped)
                if g is not None and lvl is not None:
                    set_group_brightness(g, int(lvl))
                    lighting.start_session(user_id, g, int(lvl), step=step)
                    recent_action_setter(user_id, "lighting", group=g, level=int(lvl), verb="adjust")
                    return msg

            # Fallback for emphasis phrases even if parser didn't resolve
            if delta is None:
                if "way down" in low:
                    delta = -step
                elif "way up" in low:
                    delta = step

            # Still nothing -> chat
            if delta is None:
                return safe_chat(brain, user_id, text_stripped)

            # Normalize tiny deltas to a 10% step
            try:
                delta = int(delta)
            except Exception:
                delta = 0
            if 0 < abs(delta) < step:
                delta = step if delta > 0 else -step

            # Intensify for emphasis like "way way", caps, etc.
            mult = normalize._intensity_multiplier(text_stripped)
            if delta:
                delta = int(delta) * mult

            new_level = normalize._clamp_level(current_level + delta)
            last_delta = delta

        set_group_brightness(target_group, new_level)
        lighting.start_session(user_id, target_group, new_level, step=step)

        # keep last_delta inside lighting session:
        s = lighting.get_session(user_id)
        if s is not None:
            s["last_delta"] = int(last_delta)

        recent_action_setter(user_id, "lighting", group=target_group, level=new_level, verb="adjust")

        nice_name = target_group.replace("_", " ")
        percent = round(new_level / 10)

        inject_state_fn(brain, f"I set {nice_name} lights to {percent} percent.")

        style = normalize._reply_style_for_lights(text_stripped)

        if style == "short":
            if new_level == 0:
                return safe_chat(brain, user_id, f"Done. {nice_name} off.")
            if mode == "max":
                return safe_chat(brain, user_id, f"Done. {nice_name} maxed.")
            return safe_chat(brain, user_id, f"Set {nice_name} to {percent}%.")

        return safe_chat(
            brain,
            user_id,
            f"User said: '{text_stripped}'. "
            f"{nice_name} lights are now at {percent}%. "
            f"Reply like Ash: playful, human, natural. "
            f"If user sounded annoyed or uncomfortable, tease lightly."
        )

    # If we got here, treat as chat
    return safe_chat(brain, user_id, text_stripped)
