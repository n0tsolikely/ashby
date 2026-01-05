"""
Truth Gate: prevents chat-mode hallucinations that contradict Ashby’s reality.

This should NEVER block real actions — it only post-processes chat output.
"""

from __future__ import annotations

FORBIDDEN_PHRASES = [
    "i can't control",
    "i can’t control",
    "i don't have access",
    "i don’t have access",
    "i do not have access",
    "i'm unable to",
    "i’m unable to",
    "as an ai",
    "i'm just",
    "i am just",
    "i cannot",
]

DEFAULT_REJECT = "Nah — that reply was bullshit. Say it again."


def apply(reply: str) -> str:
    low = (reply or "").lower()
    if any(p in low for p in FORBIDDEN_PHRASES):
        return DEFAULT_REJECT
    return reply
