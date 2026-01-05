import json
import os
from typing import Dict, Any

from openai import OpenAI
from .intent_schema import make_intent

# You can override this with an env var later if you want
MODEL_NAME = os.getenv("ASHBY_NLU_MODEL", "gpt-4o-mini")

client = OpenAI()


def gpt_extract_intent(text: str) -> Dict[str, Any]:
    """
    Use GPT to turn a raw user message into a normalized Ashby intent dict.
    """
    # DEBUG: see when GPT is actually being used
    print(f"[Ashby NLU] GPT intent called for: {text!r}")

    system_msg = (
        "You are an intent classifier for a home automation assistant called Ashby. "
        "Read the user's message and return ONLY a JSON object with this exact shape:\n"
        "{"
        "\"type\": one of [\"lights.on\", \"lights.off\", \"lights.adjust\", \"comfort.cold\", \"chat\"], "
        "\"group\": string or null, "
        "\"brightness\": integer or null, "
        "\"delta\": integer or null, "
        "\"mode\": string or null"
        "}\n"
        "No explanations, no extra text, just JSON."
    )

    user_msg = f'User message: "{text}"'

    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=150,
        temperature=0,
    )

    raw = resp.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
    except Exception:
        # If GPT does something weird, just treat it as normal chat
        return make_intent("chat")

    intent_type = data.get("type", "chat")
    if intent_type not in ["lights.on", "lights.off", "lights.adjust", "comfort.cold", "chat"]:
        intent_type = "chat"

    return make_intent(
        type=intent_type,
        group=data.get("group"),
        brightness=data.get("brightness"),
        delta=data.get("delta"),
        mode=data.get("mode"),
    )
