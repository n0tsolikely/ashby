from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class TranscriptSegmentPayload(BaseModel):
    segment_id: str = Field(min_length=1)
    start_ms: int
    end_ms: int
    speaker_label: str = Field(min_length=1)
    speaker_name: Optional[str] = None
    text: str = Field(min_length=1)


class TemplateSectionPayload(BaseModel):
    heading: str = Field(min_length=1)
    target_key: Optional[str] = None
    order: int


RetentionLiteral = Literal["LOW", "MED", "HIGH", "NEAR-VERBATIM"]
ModeLiteral = Literal["meeting", "journal"]
ProfileLiteral = Literal["LOCAL_ONLY", "HYBRID", "CLOUD_ONLY", "CLOUD"]


class FormalizeRequest(BaseModel):
    transcript_text: Optional[str] = None
    transcript_segments: Optional[list[TranscriptSegmentPayload]] = None
    mode: ModeLiteral
    template_id: str = Field(min_length=1)
    retention: RetentionLiteral
    profile: ProfileLiteral = "HYBRID"
    template_text: Optional[str] = None
    template_sections: Optional[list[TemplateSectionPayload]] = None
    include_citations: bool = False
    show_empty_sections: bool = False

    @field_validator("template_id")
    @classmethod
    def _template_id_not_blank(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("template_id must not be blank")
        return v

    @field_validator("retention", mode="before")
    @classmethod
    def _normalize_retention(cls, value: Any) -> str:
        v = str(value).strip().upper().replace("_", "-")
        return v

    @field_validator("profile", mode="before")
    @classmethod
    def _normalize_profile(cls, value: Any) -> str:
        return str(value).strip().upper()

    @field_validator("transcript_text", mode="before")
    @classmethod
    def _normalize_transcript_text(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        v = str(value).strip()
        return v or None


class GatewayUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    char_count: Optional[int] = None


class FormalizeResponse(BaseModel):
    version: int = 1
    request_id: str
    output_json: Dict[str, Any]
    evidence_map: Dict[str, Any] = Field(default_factory=dict)
    usage: GatewayUsage = Field(default_factory=GatewayUsage)
    timing_ms: int
    provider: str
    model: str


class ErrorResponse(BaseModel):
    ok: bool = False
    version: int = 1
    request_id: str
    error: Dict[str, Any]


class ChatEvidenceSegmentPayload(BaseModel):
    session_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    segment_id: int
    text: str = Field(min_length=1)
    speaker_label: Optional[str] = None
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    source_path: Optional[str] = None


class ChatHistoryItemPayload(BaseModel):
    role: Literal["user", "assistant", "system"]
    text: str = Field(min_length=1)


class ChatGatewayRequest(BaseModel):
    question: str = Field(min_length=1)
    scope: Literal["session", "global"] = "session"
    ui_state: Dict[str, Any] = Field(default_factory=dict)
    history_tail: list[ChatHistoryItemPayload] = Field(default_factory=list)
    evidence_segments: list[ChatEvidenceSegmentPayload] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def _question_not_blank(cls, value: str) -> str:
        out = value.strip()
        if not out:
            raise ValueError("question must not be blank")
        return out


class ChatCitationPayload(BaseModel):
    session_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    segment_id: int
    t_start_ms: Optional[int] = None
    t_end_ms: Optional[int] = None
    speaker_label: Optional[str] = None


class ChatActionPayload(BaseModel):
    kind: Literal["open_session", "jump_to_segment"]
    session_id: str = Field(min_length=1)
    run_id: Optional[str] = None
    transcript_version_id: Optional[str] = None
    segment_id: Optional[int] = None


class ChatOutputV1(BaseModel):
    text: str = Field(min_length=1)
    citations: list[ChatCitationPayload] = Field(default_factory=list)
    actions: list[ChatActionPayload] = Field(default_factory=list)


class ChatGatewayResponse(BaseModel):
    version: int = 1
    request_id: str
    output_json: Dict[str, Any]
    usage: GatewayUsage = Field(default_factory=GatewayUsage)
    timing_ms: int
    provider: str
    model: str
