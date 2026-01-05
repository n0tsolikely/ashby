import time
from typing import Dict, Any, Optional

from ashby.brain.ash_core import AshBrain
from ashby.brain.memory import memory
from ashby.brain.sessions import lighting
from ashby.brain.nlu.nlu_manager import extract_intent

from ashby.core import normalize
from ashby.core.safe_chat import safe_chat

from ashby.capabilities.lights.handler import handle_lights_intent
from ashby.capabilities.comfort.handler import handle_comfort_intent


# Keep brains alive in long-running process (Telegram bot, etc.)
_brains: Dict[str, AshBrain] = {}

# Recent actions for short-term contextual replies (per user)
_recent_actions: Dict[str, Dict[str, Any]] = {}


def _set_recent_action(user_id: str, action_type: str, **data: Any) -> None:
    rec = {"type": action_type, "ts": time.time(), **data}
    _recent_actions[str(user_id)] = rec

    # Persist a lightweight action log to memory so Ashby can "remember" actions
    # even if the process restarts.
    try:
        log = memory.get(user_id, "action_log", default=[])
        if not isinstance(log, list):
            log = []
        log.append(rec)
        log = log[-50:]
        memory.set(user_id, "action_log", log)
        memory.set(user_id, "last_action", rec)
    except Exception:
        pass


def _get_recent_action(user_id: str, max_age: float = 30.0) -> Optional[Dict[str, Any]]:
    rec = _recent_actions.get(str(user_id))
    if not rec:
        return None
    if time.time() - rec.get("ts", 0) > max_age:
        return None
    return rec


def inject_state(brain: AshBrain, note: str) -> None:
    """
    Inject a factual system-state update so Ashby knows what he just did.
    This is NOT user-visible chat.
    """
    brain.history.append({
        "role": "system",
        "content": f"SYSTEM STATE UPDATE: {note}"
    })


def get_brain(user_id: str) -> AshBrain:
    user_id = str(user_id)
    if user_id not in _brains:
        _brains[user_id] = AshBrain(user_id)
    return _brains[user_id]


def handle_text(user_id: str, text: str) -> str:
    """
    Main entrypoint for Ashby brain.

    Pipeline:
      1) Comfort session followups (yes/no/a bit more)
      2) NLU intent extraction
      3) Pending-target merge (turn it on -> which lights? -> thor)
      4) Action routing (lights/comfort)
      5) Chat fallback through safe_chat()
    """

    user_id = str(user_id)
    text_stripped = (text or "").strip()
    if not text_stripped:
        return ""

    brain = get_brain(user_id)

    # ------------------------------------------------------------
    # 1) Comfort handler (active session followups) — BEFORE NLU
    # ------------------------------------------------------------
    out = handle_comfort_intent(
        brain=brain,
        user_id=user_id,
        text_stripped=text_stripped,
        intent={"type": "unknown"},
        recent_action_setter=_set_recent_action,
    )
    if out is not None:
        return out

    # ------------------------------------------------------------
    # 2) Run NLU on every message
    # ------------------------------------------------------------
    intent = extract_intent(text_stripped)

    itype = intent.get("type", "unknown")
    group = intent.get("group")
    brightness = intent.get("brightness")
    delta = intent.get("delta")
    mode = intent.get("mode")

    low = text_stripped.lower().strip()

    # ------------------------------------------------------------
    # 3) Comfort handler (comfort.cold trigger) — AFTER NLU
    # ------------------------------------------------------------
    out = handle_comfort_intent(
        brain=brain,
        user_id=user_id,
        text_stripped=text_stripped,
        intent=intent,
        recent_action_setter=_set_recent_action,
    )
    if out is not None:
        return out

    # ------------------------------------------------------------
    # 4) FORCE LIGHT INTENTS FROM VIBE PHRASES if a lighting session is active
    # ------------------------------------------------------------
    sess = lighting.get_session(user_id)

    if sess and sess.get("group"):
        active_group = sess["group"]

        if ("turn it off" in low) or ("shut it off" in low) or ("kill it" in low) or ("shut it" in low) or ("lights off" in low):
            itype = "lights.off"
            group = group or active_group

        elif ("turn off" in low) and (not group):
            itype = "lights.off"
            group = active_group

        elif (
            ("too bright" in low)
            or ("way too bright" in low)
            or ("little bright" in low)
            or ("kind of bright" in low)
            or ("kinda bright" in low)
            or ("bright in here" in low)
            or ("it's bright" in low)
            or ("its bright" in low)
        ):
            itype = "lights.adjust"
            group = group or active_group
            if delta is None and brightness is None:
                delta = -100

    # ------------------------------------------------------------
    # 5) VIBE PHRASE CLARIFIER when NO active lighting session
    # ------------------------------------------------------------
    if (not sess) and (not str(itype).startswith("lights.")):

        if ("bright in here" in low) or ("dark in here" in low) or ("too bright" in low) or ("too dark" in low):
            lighting.set_awaiting_target(user_id, {"type": "lights.adjust", "needs_confirm": True})
            return safe_chat(brain, user_id, "You mean the lights in here? Want me to dim them a bit?")

        if ("bright out" in low) or ("dark out" in low) or ("sunny" in low):
            return safe_chat(brain, user_id, "Yeah? Sunny as hell out there or what?")

    # ------------------------------------------------------------
    # 6) Pending target merge:
    # If we were waiting for a target and they reply "thor" etc.
    # ------------------------------------------------------------
    pending = lighting.pop_awaiting_target(user_id)

    if pending and pending.get("type") == "lights.on":
        if not group:
            guess = normalize._normalize_group_from_free_text(text_stripped)
            if guess not in ["turn_it_on", "turn_it_off", "on", "off"]:
                group = guess

        if brightness is None and pending.get("brightness") is not None:
            brightness = pending["brightness"]
        if mode is None and pending.get("mode") is not None:
            mode = pending["mode"]

        if group and not str(itype).startswith("lights."):
            itype = "lights.on"

    # ------------------------------------------------------------
    # 7) “That’s perfect / better” acknowledgement after a light change
    # ------------------------------------------------------------
    recent = _get_recent_action(user_id)

    if recent and recent.get("type") == "lighting" and itype in ("chat", "unknown"):
        ack_keywords = [
            "perfect",
            "better",
            "much better",
            "nice",
            "good",
            "awesome",
            "sweet",
            "great"
            "beauty",
            "thanks",
            "thank you",
            "that’s good",
            "that is good",
            "that’s better",
            "that is better",
            "mint",
            "cool",
            "right on",
            "ballin",
            "bet",
            "you're the man",
            "badass",
        ]
        if any(k in low for k in ack_keywords):
            grp = recent.get("group")
            level = recent.get("level")
            if grp is not None and level is not None:
                try:
                    memory.set(user_id, f"preferred_level_{grp}", int(level))
                except Exception:
                    pass
                percent = round(int(level) / 10)
                return f"Gotcha. Leaving {str(grp).replace('_',' ')} around {percent}%."
            return "Got it — leaving it like that."

    # ------------------------------------------------------------
    # 8) Lights handler dispatch
    # ------------------------------------------------------------
    if str(itype).startswith("lights."):
        out = handle_lights_intent(
            brain=brain,
            user_id=user_id,
            text_stripped=text_stripped,
            intent={
                "type": itype,
                "group": group,
                "brightness": brightness,
                "delta": delta,
                "mode": mode,
            },
            recent_action_getter=_get_recent_action,
            recent_action_setter=_set_recent_action,
            inject_state_fn=inject_state,
        )
        if out is not None:
            return out

    # ------------------------------------------------------------
    # 9) Chat fallback
    # ------------------------------------------------------------
    return safe_chat(brain, user_id, text_stripped)
