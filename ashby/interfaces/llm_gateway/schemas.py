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
