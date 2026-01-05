import time

_sessions = {}

TIMEOUT = 10      # seconds for the "heat adjust" window
TEMP_STEP = 1.0   # how much to bump per "a little" / "one more" in °C


def start_cold_session(user_id: str, current_temp: float, preferred_temp: float):
    """
    Start a 'I'm cold' comfort session.

    current_temp   = what the thermostat says now
    preferred_temp = what this user usually likes (from memory or default)
    """
    user_id = str(user_id)
    proposed = preferred_temp
    _sessions[user_id] = {
        "current": float(current_temp),
        "preferred": float(preferred_temp),
        "proposed": float(proposed),
        "updated": time.time(),
    }
    return _sessions[user_id]


def end_session(user_id: str):
    user_id = str(user_id)
    if user_id in _sessions:
        del _sessions[user_id]


def has_active_session(user_id: str) -> bool:
    user_id = str(user_id)
    s = _sessions.get(user_id)
    if not s:
        return False
    if (time.time() - s["updated"]) > TIMEOUT:
        end_session(user_id)
        return False
    return True


def process_reply(user_id: str, phrase: str):
    """
    Handle follow-ups like:
      - "yes", "sure", "do it"
      - "a little", "just a bit"
      - "one more", "more"
      - "no", "nah", "leave it"

    Returns: (target_temp or None, message)
    If target_temp is not None, caller should actually set the heat.
    """
    user_id = str(user_id)
    if not has_active_session(user_id):
        return None, "No active heat adjustment session."

    s = _sessions[user_id]
    phrase = phrase.lower().strip()
    s["updated"] = time.time()

    # Confirm: set to proposed
    if phrase in ["yes", "sure", "do it", "ok", "okay"]:
        temp = s["proposed"]
        end_session(user_id)
        return temp, f"Turning heat up to {temp}°C."

    # Small nudge from current
    if phrase in ["a little", "just a bit", "a bit"]:
        s["proposed"] = s["current"] + TEMP_STEP
        return s["proposed"], f"Okay, nudging it up to {s['proposed']}°C."

    # More again
    if phrase in ["one more", "more", "bit more"]:
        s["proposed"] += TEMP_STEP
        return s["proposed"], f"Alright, adjusting heat to {s['proposed']}°C."

    # Cancel
    if phrase in ["no", "nah", "leave it", "cancel"]:
        end_session(user_id)
        return None, "Got it — leaving the heat as it is."

    return None, "Not sure what you mean about the heat."
