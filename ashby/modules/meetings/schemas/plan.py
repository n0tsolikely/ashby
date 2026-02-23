from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class IntentKind(str, Enum):
    SET_MODE = "set_mode"
    SET_SPEAKERS = "set_speakers"
    INTAKE = "intake"
    TRANSCRIBE = "transcribe"
    FORMALIZE = "formalize"
    SEARCH = "search"
    EXPORT = "export"
    SPEAKER_MAP_OVERLAY = "speaker_map_overlay"
    EXTRACT_ONLY = "extract_only"


class PlanStepKind(str, Enum):
    VALIDATE = "validate"
    SET_MODE = "set_mode"
    SET_SPEAKERS = "set_speakers"
    INTAKE = "intake"
    TRANSCRIBE = "transcribe"
    FORMALIZE = "formalize"
    SEARCH = "search"
    EXPORT = "export"
    SPEAKER_MAP_OVERLAY = "speaker_map_overlay"
    EXTRACT_ONLY = "extract_only"


@dataclass(frozen=True)
class AttachmentMeta:
    filename: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None


@dataclass(frozen=True)
class UIState:
    mode: Optional[str] = None
    template: Optional[str] = None
    retention: Optional[str] = None
    speakers: Optional[Union[int, str]] = None  # int or "auto"
    diarization_enabled: Optional[bool] = None
    transcript_version_id: Optional[str] = None


@dataclass(frozen=True)
class SessionContext:
    active_session_id: Optional[str] = None
    last_run_id: Optional[str] = None


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    field: Optional[str] = None


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: List[ValidationIssue] = field(default_factory=list)


@dataclass(frozen=True)
class MeetingsIntent:
    kind: IntentKind
    raw_text: str = ""
    mode: Optional[str] = None
    template: Optional[str] = None
    retention: Optional[str] = None
    speakers: Optional[Union[int, str]] = None
    query: Optional[str] = None
    export_format: Optional[str] = None
    overlay: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class PlanStep:
    kind: PlanStepKind
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MeetingsPlan:
    """
    Machine-checkable, ordered execution steps.
    NOTE: Clarification + 'go' gating is handled in QUEST_017/018.
    """
    intent: MeetingsIntent
    steps: List[PlanStep]
    validation: ValidationResult
