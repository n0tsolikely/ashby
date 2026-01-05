"""
safe_chat

Chat wrapper used by the router to keep Ashby grounded:
- Builds context snapshot
- Calls AshBrain.chat()
- Applies truth gate (no fake “I can’t” replies)
"""

from __future__ import annotations

from ashby.core import context_snapshot, truth_gate
from ashby.brain.sessions import lighting
from ashby.brain.memory import memory
from ashby.brain.ash_core import AshBrain


def safe_chat(brain: AshBrain, user_id: str, text: str) -> str:
    """
    Chat wrapper to reject LLM hallucinations that break Ashby realism.
    This NEVER blocks real actions — chat only.
    Also injects state context so Ashby "knows" what it did / what’s going on.
    """

    # --- Build state injection context ---
    # Lighting session state (in-memory session manager)
    ls = lighting.get_session(user_id)

    # Heat prefs / known temp (from memory)
    preferred_temp = memory.get(user_id, "preferred_temp", 21.0)
    last_known_temp = memory.get(user_id, "last_known_temp", None)

    # Recent action
    last_action = memory.get(user_id, "last_action", default=None)

    injected = context_snapshot.build_snapshot(
        user_id=str(user_id),
        user_text=text,
        lighting_session=ls,
        preferred_temp=preferred_temp,
        last_known_temp=last_known_temp,
        last_action=last_action,
    )

    reply = brain.chat(injected)
    reply = truth_gate.apply(reply)
    return reply
