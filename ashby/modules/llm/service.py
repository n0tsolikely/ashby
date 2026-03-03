from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Protocol


@dataclass(frozen=True)
class TranscriptSegmentPayload:
    segment_id: str
    start_ms: int
    end_ms: int
    speaker_label: str
    text: str
    speaker_name: Optional[str] = None


@dataclass(frozen=True)
class TemplateSectionPayload:
    heading: str
    order: int
    target_key: Optional[str] = None


@dataclass(frozen=True)
class LLMFormalizeRequest:
    mode: str
    template_id: str
    retention: str
    profile: str
    transcript_text: Optional[str] = None
    transcript_segments: Optional[list[TranscriptSegmentPayload]] = None
    template_text: Optional[str] = None
    template_sections: Optional[list[TemplateSectionPayload]] = None
    include_citations: bool = False
    show_empty_sections: bool = False

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "mode": self.mode,
            "template_id": self.template_id,
            "retention": self.retention,
            "profile": self.profile,
            "include_citations": self.include_citations,
            "show_empty_sections": self.show_empty_sections,
        }
        if self.transcript_text is not None:
            payload["transcript_text"] = self.transcript_text
        if self.transcript_segments is not None:
            payload["transcript_segments"] = [
                {
                    "segment_id": s.segment_id,
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "speaker_label": s.speaker_label,
                    "speaker_name": s.speaker_name,
                    "text": s.text,
                }
                for s in self.transcript_segments
            ]
        if self.template_text is not None:
            payload["template_text"] = self.template_text
        if self.template_sections is not None:
            payload["template_sections"] = [
                {"heading": s.heading, "target_key": s.target_key, "order": s.order}
                for s in self.template_sections
            ]
        return payload


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
