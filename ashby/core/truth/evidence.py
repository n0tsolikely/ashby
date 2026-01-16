from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from ashby.core.results import ActionResult, ArtifactResult, ErrorResult, from_dict as result_from_dict
from ashby.interfaces.storage import validate_rel_path


Severity: TypeAlias = Literal["block", "warn"]


def _require_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")
    if value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")
    return value


def _optional_str(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str or None")
    return value


def _optional_int_ms(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int or None")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _require_dict(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")
    return value


@dataclass(kw_only=True)
class Citation:
    """
    Pointer into a durable artifact (platform-wide useful).

    Required:
    - session_id: str
    - artifact_path: str   (relative path under artifact storage root)

    Optional:
    - segment_id: str | None
    - start_ms: int | None
    - end_ms: int | None
    - speaker_id: str | None
    """

    session_id: str
    artifact_path: str
    segment_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    speaker_id: str | None = None

    def __post_init__(self) -> None:
        self.session_id = _require_str(self.session_id, field_name="session_id")
        self.artifact_path = _require_str(self.artifact_path, field_name="artifact_path")
        validate_rel_path(self.artifact_path, allow_empty=False)

        self.segment_id = _optional_str(self.segment_id, field_name="segment_id")
        self.speaker_id = _optional_str(self.speaker_id, field_name="speaker_id")

        self.start_ms = _optional_int_ms(self.start_ms, field_name="start_ms")
        self.end_ms = _optional_int_ms(self.end_ms, field_name="end_ms")

        if self.start_ms is not None and self.end_ms is not None and self.start_ms > self.end_ms:
            raise ValueError("start_ms must be <= end_ms")

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "artifact_path": self.artifact_path,
            "segment_id": self.segment_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "speaker_id": self.speaker_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Citation":
        if not isinstance(d, dict):
            raise TypeError("Citation.from_dict expects a dict")
        if "session_id" not in d or "artifact_path" not in d:
            raise ValueError("Citation dict must include 'session_id' and 'artifact_path'")
        return cls(
            session_id=d["session_id"],
            artifact_path=d["artifact_path"],
            segment_id=d.get("segment_id", None),
            start_ms=d.get("start_ms", None),
            end_ms=d.get("end_ms", None),
            speaker_id=d.get("speaker_id", None),
        )


@dataclass(kw_only=True)
class EvidenceBundle:
    """
    Aggregates all evidence available to constrain a response draft.

    This is purely descriptive and must never execute actions.
    """

    action_results: list[ActionResult] = field(default_factory=list)
    artifact_results: list[ArtifactResult] = field(default_factory=list)
    errors: list[ErrorResult] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.action_results, list):
            raise TypeError("action_results must be a list[ActionResult]")
        for r in self.action_results:
            if not isinstance(r, ActionResult):
                raise TypeError("action_results must be a list[ActionResult]")

        if not isinstance(self.artifact_results, list):
            raise TypeError("artifact_results must be a list[ArtifactResult]")
        for r in self.artifact_results:
            if not isinstance(r, ArtifactResult):
                raise TypeError("artifact_results must be a list[ArtifactResult]")

        if not isinstance(self.errors, list):
            raise TypeError("errors must be a list[ErrorResult]")
        for r in self.errors:
            if not isinstance(r, ErrorResult):
                raise TypeError("errors must be a list[ErrorResult]")

        if not isinstance(self.citations, list):
            raise TypeError("citations must be a list[Citation]")
        for c in self.citations:
            if not isinstance(c, Citation):
                raise TypeError("citations must be a list[Citation]")

        if not isinstance(self.notes, list):
            raise TypeError("notes must be a list[str]")
        for n in self.notes:
            if not isinstance(n, str):
                raise TypeError("notes must be a list[str]")

    @classmethod
    def empty(cls) -> "EvidenceBundle":
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_results": [r.to_dict() for r in self.action_results],
            "artifact_results": [r.to_dict() for r in self.artifact_results],
            "errors": [r.to_dict() for r in self.errors],
            "citations": [c.to_dict() for c in self.citations],
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvidenceBundle":
        if not isinstance(d, dict):
            raise TypeError("EvidenceBundle.from_dict expects a dict")

        action_results: list[ActionResult] = []
        for item in d.get("action_results", []) or []:
            r = result_from_dict(item)
            if not isinstance(r, ActionResult):
                raise TypeError("action_results items must be ActionResult dicts")
            action_results.append(r)

        artifact_results: list[ArtifactResult] = []
        for item in d.get("artifact_results", []) or []:
            r = result_from_dict(item)
            if not isinstance(r, ArtifactResult):
                raise TypeError("artifact_results items must be ArtifactResult dicts")
            artifact_results.append(r)

        errors: list[ErrorResult] = []
        for item in d.get("errors", []) or []:
            r = result_from_dict(item)
            if not isinstance(r, ErrorResult):
                raise TypeError("errors items must be ErrorResult dicts")
            errors.append(r)

        citations: list[Citation] = []
        for item in d.get("citations", []) or []:
            citations.append(Citation.from_dict(item))

        notes = d.get("notes", []) or []
        if not isinstance(notes, list):
            raise TypeError("notes must be a list[str]")
        for n in notes:
            if not isinstance(n, str):
                raise TypeError("notes must be a list[str]")

        return cls(
            action_results=action_results,
            artifact_results=artifact_results,
            errors=errors,
            citations=citations,
            notes=notes,
        )


@dataclass(kw_only=True)
class TruthViolation:
    """
    Structured report that a draft violates truth policy.
    """

    code: str
    message: str
    severity: Severity
    evidence_required: bool
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.code = _require_str(self.code, field_name="code")
        self.message = _require_str(self.message, field_name="message")

        if self.severity not in ("block", "warn"):
            raise ValueError("severity must be 'block' or 'warn'")

        if not isinstance(self.evidence_required, bool):
            raise TypeError("evidence_required must be a bool")

        self.meta = _require_dict(self.meta, field_name="meta")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "evidence_required": self.evidence_required,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TruthViolation":
        if not isinstance(d, dict):
            raise TypeError("TruthViolation.from_dict expects a dict")
        if "code" not in d or "message" not in d or "severity" not in d or "evidence_required" not in d:
            raise ValueError("TruthViolation dict missing required fields")
        meta = d.get("meta", {}) or {}
        return cls(
            code=d["code"],
            message=d["message"],
            severity=d["severity"],
            evidence_required=d["evidence_required"],
            meta=meta,
        )
