import os
import difflib
from typing import Dict, List, Tuple, Optional

from .intent_schema import make_intent

# --------------------------------------------------------------------
# Existing alias-based helpers (group detection)
# --------------------------------------------------------------------

GROUP_ALIASES = {
    "captain": "captain_america",
    "america": "captain_america",
    "captain america": "captain_america",
    "thor": "thor",
    "sky": "sky",
}

def detect_group(text: str):
    t = text.lower()
    for alias, real in GROUP_ALIASES.items():
        if alias in t:
            return real
    return None

def detect_max(text: str):
    words = [
        "max",
        "full",
        "full blast",
        "maximum",
        "all the way",
        "super bright",
        "bright as fuck",
        "bright af",
        "blinding",
        "sun mode",
        "bro bright",
    ]
    t = text.lower()
    return any(w in t for w in words)

def detect_adjust(text: str):
    t = text.lower()
    if any(w in t for w in ["darker", "dim", "less", "lower"]):
        return -100
    if any(w in t for w in ["brighter", "lighter", "more", "higher"]):
        return +100
    return None

def detect_on_off(text: str):
    t = text.lower()
    if "turn on" in t or "switch on" in t:
        return "lights.on"
    if "turn off" in t or "switch off" in t:
        return "lights.off"
    return None

def detect_cold(text: str):
    return any(w in text.lower() for w in ["cold", "freezing", "chilly"])

# --------------------------------------------------------------------
# NEW: lights + comfort examples file (lights + comfort only)
# --------------------------------------------------------------------

NLU_DATA_FILE = os.path.join(
    os.path.dirname(__file__),
    "examples/nlu_lights_comfort_eg.txt",   # <— your file
)

_EXAMPLES: Dict[str, List[str]] = {}
_LOADED = False

def _load_examples() -> None:
    """Load intent<TAB>utterance lines from the lights+comfort examples file."""
    global _LOADED, _EXAMPLES
    if _LOADED:
        return

    if not os.path.exists(NLU_DATA_FILE):
        # If the file isn't there, just skip; local NLU will still work with
        # the hard-coded rules and GPT via nlu_manager.
        _LOADED = True
        _EXAMPLES = {}
        return

    examples: Dict[str, List[str]] = {}
    with open(NLU_DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "\t" not in line:
                continue
            intent, utterance = line.split("\t", 1)
            intent = intent.strip()
            utt = utterance.strip().lower()
            examples.setdefault(intent, []).append(utt)

    _EXAMPLES = examples
    _LOADED = True

def _classify_from_examples(text: str) -> Tuple[Optional[str], float]:
    """
    Fuzzy match the text against all lights/comfort examples.

    Returns:
        (best_intent_label, score) or (None, 0.0)
    """
    _load_examples()
    if not _EXAMPLES:
        return None, 0.0

    text_norm = text.strip().lower()
    if not text_norm:
        return None, 0.0

    best_intent: Optional[str] = None
    best_score: float = 0.0

    for intent, utterances in _EXAMPLES.items():
        for utt in utterances:
            score = difflib.SequenceMatcher(a=text_norm, b=utt).ratio()
            if score > best_score:
                best_score = score
                best_intent = intent

    return best_intent, best_score

def _map_example_intent(label: str, text: str):
    """
    Map a label from the examples file into our existing schema:
      - lights.on
      - lights.off
      - lights.adjust (with +/-100 delta hints)
      - comfort.cold
      - chat
      - unknown
    We only care about **lights** and **comfort** here.
    """

    # Lights on/off
    if label.startswith("lights.on"):
        return make_intent("lights.on", group=detect_group(text))

    if label.startswith("lights.off"):
        return make_intent("lights.off", group=detect_group(text))

    # Relative brightness more/less
    if label == "lights.adjust_more":
        return make_intent("lights.adjust", group=detect_group(text), delta=+100)

    if label == "lights.adjust_less":
        return make_intent("lights.adjust", group=detect_group(text), delta=-100)

    # Absolute / percent delta → still "lights.adjust", router/GPT refines if needed
    if label in ("lights.set_absolute", "lights.adjust_percent_delta"):
        return make_intent("lights.adjust", group=detect_group(text))

    # Comfort – for now everything maps into comfort.cold (same type you already use),
    # we can split comfort.hot / comfort.cold later if we extend the schema.
    if label.startswith("comfort.too_cold") \
       or label.startswith("comfort.too_hot") \
       or label.startswith("comfort.set_temp") \
       or label.startswith("comfort.ack"):
        return make_intent("comfort.cold")

    # Any "chat-like" labels (if they exist in the file)
    if label.startswith("chat.") or label.startswith("meta.help"):
        return make_intent("chat")

    # Anything else → let GPT handle it via nlu_manager
    return make_intent("unknown")

# --------------------------------------------------------------------
# Main local NLU entry
# --------------------------------------------------------------------

def local_extract_intent(text: str):
    """
    Local NLU for Ashby (lights + comfort).

    Order:
      1. Hard-coded comfort.cold (simple keyword check)
      2. Hard-coded lights on/off
      3. Hard-coded brightness up/down
      4. Hard-coded max brightness
      5. Fuzzy match using nlu_lights_comfort_eg.txt
      6. If still unknown → GPT via nlu_manager
    """
    # Step 1: comfort (cold)
    if detect_cold(text):
        return make_intent("comfort.cold")

    # Step 2: lights on/off
    onoff = detect_on_off(text)
    if onoff:
        return make_intent(onoff, group=detect_group(text))

    # Step 3: relative adjust
    delta = detect_adjust(text)
    if delta is not None:
        return make_intent("lights.adjust", group=detect_group(text), delta=delta)

    # Step 4: max brightness
    if detect_max(text):
        return make_intent(
            "lights.adjust",
            group=detect_group(text),
            brightness=1000,
            mode="max",
        )

    # Step 5: fallback to example-based fuzzy matching
    label, score = _classify_from_examples(text)

    HIGH_CONFIDENCE = 0.82  # tune this later if needed
    if label and score >= HIGH_CONFIDENCE:
        return _map_example_intent(label, text)

    # Step 6: unknown → nlu_manager will push it to GPT
    return make_intent("unknown")
