from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ClarifyField(str, Enum):
    MODE = "mode"
    TEMPLATE = "template"
    SPEAKERS = "speakers"


@dataclass(frozen=True)
class ClarifyOption:
    value: str
    label: Optional[str] = None


@dataclass(frozen=True)
class ClarifyPrompt:
    """
    Doors render this directly (web/telegram/cli) without embedding business logic.
    """
    message: str
    fields_needed: List[ClarifyField]
    options: Dict[ClarifyField, List[ClarifyOption]] = field(default_factory=dict)
    notes: Optional[str] = None


@dataclass(frozen=True)
class PlanPreview:
    mode: str
    template: str
    speakers: str
    defaults_used: List[str]
    ordered_steps: List[Dict[str, Any]]
    ambiguities: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClarifyOrPreview:
    needs_clarification: bool
    clarify: Optional[ClarifyPrompt] = None
    preview: Optional[PlanPreview] = None
