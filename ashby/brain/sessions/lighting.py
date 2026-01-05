import time

# One active lighting session per user_id
_sessions = {}

# Pending "turn it on" style intents waiting for a target
_pending_targets = {}

SESSION_TIMEOUT = 30      # seconds
DEFAULT_STEP = 100        # brightness points (0–1000 scale)


def start_session(user_id: str, group: str, initial_level: int, step: int = DEFAULT_STEP):
    """Start or reset a lighting session for this user."""
    user_id = str(user_id)
    _sessions[user_id] = {
        "group": group,
        "level": int(initial_level),
        "step": int(step),
        "last_delta": 0,
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
    if (time.time() - s["updated"]) > SESSION_TIMEOUT:
        end_session(user_id)
        return False
    return True


def get_session(user_id: str):
    """Return the current session dict or None (auto-expiring)."""
    user_id = str(user_id)
    if not has_active_session(user_id):
        return None
    return _sessions[user_id]


def set_awaiting_target(user_id: str, pending_intent: dict):
    """Store an unresolved lighting intent (e.g. 'turn it on' with no target)."""
    user_id = str(user_id)
    _pending_targets[user_id] = pending_intent


def pop_awaiting_target(user_id: str):
    """Return and clear the pending intent if one exists."""
    user_id = str(user_id)
    intent = _pending_targets.get(user_id)
    if user_id in _pending_targets:
        del _pending_targets[user_id]
    return intent


def process_adjust_phrase(user_id: str, phrase: str):
    """
    Handle 'darker', 'brighter', 'one more', 'back one', 'kill it'.
    Returns: (group, new_level, message)
    If no change is made, group/new_level may be None.
    """
    user_id = str(user_id)
    s = get_session(user_id)
    if not s:
        return None, None, "No active lighting session."

    phrase = phrase.lower().strip()

    # Kill / off
    if phrase in ["kill it", "off", "shut it down", "lights out"]:
        group = s["group"]
        end_session(user_id)
        return group, 0, "Lights off."

    # Determine delta
    if phrase in ["darker", "dim", "less"]:
        delta = -s["step"]
    elif phrase in ["brighter", "lighter", "more"]:
        delta = +s["step"]
    elif phrase in ["one more", "another", "bit more"]:
        delta = +s["step"]
    elif phrase in ["back one", "too far", "go back"]:
        delta = -s["last_delta"]
    else:
        return None, None, "I don't understand that lighting adjustment."

    new_level = max(0, min(1000, s["level"] + delta))
    s["last_delta"] = delta
    s["level"] = new_level
    s["updated"] = time.time()

    group = s["group"]
    percent = int(new_level / 10)
    return group, new_level, f"Setting {group.replace('_', ' ')} to {percent}%."
