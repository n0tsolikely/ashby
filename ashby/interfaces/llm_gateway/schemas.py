from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


RetentionLiteral = Literal["LOW", "MED", "HIGH", "NEAR-VERBATIM"]
ModeLiteral = Literal["meeting", "journal"]
ProfileLiteral = Literal["LOCAL_ONLY", "HYBRID", "CLOUD_ONLY", "CLOUD"]


class FormalizeRequest(BaseModel):
    transcript_text: str = Field(min_length=1)
    mode: ModeLiteral
    template_id: str = Field(min_length=1)
    retention: RetentionLiteral
    profile: ProfileLiteral = "HYBRID"

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
