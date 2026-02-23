from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class TraceV1(BaseModel):
    request_id: str


class PaginationV1(BaseModel):
    limit: int = 50
    offset: int = 0
    returned: int = 0
    total: Optional[int] = None


class RunSummaryV1(BaseModel):
    run_id: str
    status: Optional[str] = None
    stage: Optional[str] = None
    progress: Optional[float] = None
    created_ts: Optional[float] = None


class SessionSummaryV1(BaseModel):
    session_id: str
    created_ts: Optional[float] = None
    mode: Optional[str] = None
    title: Optional[str] = None
    latest_run: Optional[RunSummaryV1] = None
    has_transcript: bool = False
    has_formalization: bool = False


class SessionDetailV1(BaseModel):
    session_id: str
    created_ts: Optional[float] = None
    mode: Optional[str] = None
    title: Optional[str] = None
    title_source: Literal["session_manifest", "state_override"] = "session_manifest"
    state: Dict[str, Any] = Field(default_factory=dict)
    contributions: List[Dict[str, Any]] = Field(default_factory=list)
    runs: List[RunSummaryV1] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict)


class TranscriptVersionSummaryV1(BaseModel):
    transcript_version_id: str
    session_id: Optional[str] = None
    run_id: str
    created_ts: Optional[float] = None
    segments_count: int = 0
    diarization_enabled: bool = False
    asr_engine: str = "default"
    active: bool = False


class TranscriptVersionV1(BaseModel):
    transcript_version_id: str
    run_id: str
    session_id: Optional[str] = None
    created_ts: Optional[float] = None
    diarization_enabled: bool = False
    asr_engine: str = "default"
    audio_ref: Dict[str, Any] = Field(default_factory=dict)
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    speaker_map: Dict[str, str] = Field(default_factory=dict)


class FormalizationSummaryV1(BaseModel):
    formalization_id: str
    run_id: str
    session_id: Optional[str] = None
    created_ts: Optional[float] = None
    mode: Optional[str] = None
    template_id: Optional[str] = None
    retention: Optional[str] = None
    status: Optional[str] = None
    downloads: Dict[str, Any] = Field(default_factory=dict)
    transcript_version_id: Optional[str] = None


class ExportResponseV1(BaseModel):
    session_id: str
    export_type: Literal["full_bundle", "transcript_only", "formalization_only"]
    zip: Dict[str, Any]


class ChatRequestV1(BaseModel):
    session_id: Optional[str] = None
    text: str = ""
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    ui: Dict[str, Any] = Field(default_factory=dict)
    client: Dict[str, Any] = Field(default_factory=dict)


class ChatReplyV1(BaseModel):
    text: str
    kind: Literal["planner", "system", "not_implemented"] = "system"
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)


class ChatResponseV1(BaseModel):
    session_id: Optional[str] = None
    scope: Literal["session", "global"] = "session"
    reply: ChatReplyV1
    planner: Optional[Dict[str, Any]] = None
