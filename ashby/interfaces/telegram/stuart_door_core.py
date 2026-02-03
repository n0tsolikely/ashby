from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple

Mode = Literal["meeting", "journal"]
Speakers = Literal["auto", "1", "2", "3+"]

STUART_CB_PREFIX = "stuart:"


@dataclass(frozen=True)
class DoorButton:
    label: str
    data: str


@dataclass(frozen=True)
class DoorPrompt:
    text: str
    buttons: List[DoorButton]


@dataclass
class DoorState:
    stage: str  # "awaiting_mode" | "awaiting_speakers" | "ready"
    local_path: str
    source_kind: str  # "audio" | "video" | "voice" | "document"
    mode: Optional[Mode] = None
    speakers: Optional[Speakers] = None
    # Once executed:
    session_id: Optional[str] = None
    run_id: Optional[str] = None


def start_from_upload(*, local_path: str, source_kind: str) -> Tuple[DoorState, DoorPrompt]:
    st = DoorState(stage="awaiting_mode", local_path=local_path, source_kind=source_kind)
    prompt = DoorPrompt(
        text="Stuart: pick mode",
        buttons=[
            DoorButton("Meeting", f"{STUART_CB_PREFIX}mode:meeting"),
            DoorButton("Journal/Diary", f"{STUART_CB_PREFIX}mode:journal"),
        ],
    )
    return st, prompt


def apply_mode(st: DoorState, mode: Mode) -> Tuple[DoorState, DoorPrompt]:
    st.stage = "awaiting_speakers"
    st.mode = mode
    prompt = DoorPrompt(
        text="Stuart: how many speakers?",
        buttons=[
            DoorButton("Auto", f"{STUART_CB_PREFIX}spk:auto"),
            DoorButton("1", f"{STUART_CB_PREFIX}spk:1"),
            DoorButton("2", f"{STUART_CB_PREFIX}spk:2"),
            DoorButton("3+", f"{STUART_CB_PREFIX}spk:3+"),
        ],
    )
    return st, prompt


def apply_speakers(st: DoorState, speakers: Speakers) -> DoorState:
    st.stage = "ready"
    st.speakers = speakers
    return st


def parse_callback_data(data: str) -> Optional[Tuple[str, str]]:
    # Returns (kind, value) where kind in {"mode","spk"}
    if not isinstance(data, str):
        return None
    if not data.startswith(STUART_CB_PREFIX):
        return None
    body = data[len(STUART_CB_PREFIX):]
    if ":" not in body:
        return None
    kind, value = body.split(":", 1)
    kind = kind.strip()
    value = value.strip()
    if kind not in ("mode", "spk"):
        return None
    if not value:
        return None
    return kind, value
