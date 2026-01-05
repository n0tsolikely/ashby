from typing import Dict, Any

from .local_nlu import local_extract_intent
from .gpt_nlu import gpt_extract_intent

# Mode flags
USE_HYBRID = True   # local first, GPT fallback
USE_GPT = True      # GPT-only if hybrid is False


def extract_intent(text: str) -> Dict[str, Any]:
    """
    Main entrypoint for Ashby NLU.

    Returns a normalized intent dict created via make_intent().
    """

    # Hybrid: local first, then GPT if unknown
    if USE_HYBRID:
        local_intent = local_extract_intent(text)
        if local_intent["type"] != "unknown":
            return local_intent
        # Fall back to GPT
        return gpt_extract_intent(text)

    # GPT-only mode
    if USE_GPT:
        return gpt_extract_intent(text)

    # Local-only mode (no GPT at all)
    return local_extract_intent(text)
