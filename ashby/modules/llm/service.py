from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Protocol


@dataclass(frozen=True)
class LLMFormalizeRequest:
    transcript_text: str
    mode: str
    template_id: str
    retention: str
    profile: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "transcript_text": self.transcript_text,
            "mode": self.mode,
            "template_id": self.template_id,
            "retention": self.retention,
            "profile": self.profile,
        }


@dataclass(frozen=True)
class LLMFormalizeResponse:
    version: int
    request_id: str
    output_json: Dict[str, Any]
    evidence_map: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)
    timing_ms: int = 0
    provider: str = ""
    model: str = ""


class LLMService(Protocol):
    def formalize(self, request: LLMFormalizeRequest, *, artifacts_dir: Optional[Path] = None) -> LLMFormalizeResponse:
        ...
