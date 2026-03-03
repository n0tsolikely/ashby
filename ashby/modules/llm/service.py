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


@dataclass(frozen=True)
class LLMChatEvidenceSegment:
    session_id: str
    run_id: str
    segment_id: int
    text: str
    speaker_label: Optional[str] = None
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    source_path: Optional[str] = None


@dataclass(frozen=True)
class LLMChatRequest:
    question: str
    scope: str
    ui_state: Dict[str, Any] = field(default_factory=dict)
    history_tail: list[Dict[str, Any]] = field(default_factory=list)
    evidence_segments: list[LLMChatEvidenceSegment] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "scope": self.scope,
            "ui_state": dict(self.ui_state),
            "history_tail": [dict(x) for x in self.history_tail],
            "evidence_segments": [
                {
                    "session_id": s.session_id,
                    "run_id": s.run_id,
                    "segment_id": int(s.segment_id),
                    "text": s.text,
                    "speaker_label": s.speaker_label,
                    "t_start": s.t_start,
                    "t_end": s.t_end,
                    "source_path": s.source_path,
                }
                for s in self.evidence_segments
            ],
        }


@dataclass(frozen=True)
class LLMChatResponse:
    version: int
    request_id: str
    output_json: Dict[str, Any]
    usage: Dict[str, Any] = field(default_factory=dict)
    timing_ms: int = 0
    provider: str = ""
    model: str = ""


class LLMService(Protocol):
    def formalize(self, request: LLMFormalizeRequest, *, artifacts_dir: Optional[Path] = None) -> LLMFormalizeResponse:
        ...

    def chat(self, request: LLMChatRequest, *, artifacts_dir: Optional[Path] = None) -> LLMChatResponse:
        ...
