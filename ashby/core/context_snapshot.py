"""
Context Snapshot

Builds the injected system-state snapshot used to ground chat responses.
This module does not execute actions. It only summarizes verified state and context.
"""

from __future__ import annotations
from typing import Any, Optional

def build_snapshot(
    *,
    user_id: str,
    user_text: str,
    lighting_session: Optional[dict],
    preferred_temp: Any,
    last_known_temp: Any,
    last_action: Any,
) -> str:
    # Lighting session state
    if lighting_session:
        light_ctx = (
            f"active_light_group={lighting_session.get('group')} "
            f"level={lighting_session.get('level')}/1000 "
            f"last_delta={lighting_session.get('last_delta')}"
        )
    else:
        light_ctx = "active_light_group=None"

    ctx_lines = [
        "ASHBY_STATE_SNAPSHOT:",
        f"- {light_ctx}",
        f"- preferred_temp_c={preferred_temp}",
        f"- last_known_temp_c={last_known_temp}",
        f"- last_action={last_action}",
        "",
        "IMPORTANT RULES:",
        "- You (Ashby) are the system controlling the home. Never claim you can't access/control devices.",
        "- If user asks for an action, respond like you can do it (because router will do it).",
        "- If it’s just chat, stay in-character and reference state naturally when relevant.",
        "",
        f"USER_MESSAGE: {user_text}",
    ]

    return "\n".join(str(x) for x in ctx_lines)
