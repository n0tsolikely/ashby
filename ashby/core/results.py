from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, TypeAlias

from ashby.interfaces.storage import validate_rel_path

Kind: TypeAlias = Literal["action", "artifact", "error"]


def utc_now_iso() -> str:
    """
    ISO8601 UTC timestamp string (ends with 'Z').
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _require_dict(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")
    return value


@dataclass(kw_only=True)
class ErrorInfo:
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.code = _require_str(self.code, field_name="code")
        self.message = _require_str(self.message, field_name="message")
        self.detail = _require_dict(self.detail, field_name="detail")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ErrorInfo":
        if not isinstance(d, dict):
            raise TypeError("ErrorInfo.from_dict expects a dict")
        if "code" not in d or "message" not in d:
            raise ValueError("ErrorInfo dict must include 'code' and 'message'")
        detail = d.get("detail", {})
        if detail is None:
            detail = {}
        return cls(code=d["code"], message=d["message"], detail=detail)


@dataclass(kw_only=True)
class ResultBase:
    """
    Shared fields for all results.
    """
    ok: bool
    started_at: str | None = None
    ended_at: str | None = None
    correlation_id: str | None = None
    errors: list[ErrorInfo] = field(default_factory=list)

    kind: Kind = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.ok, bool):
            raise TypeError("ok must be a bool")

        self.started_at = _optional_str(self.started_at, field_name="started_at")
        self.ended_at = _optional_str(self.ended_at, field_name="ended_at")
        self.correlation_id = _optional_str(self.correlation_id, field_name="correlation_id")

        if not isinstance(self.errors, list):
            raise TypeError("errors must be a list[ErrorInfo]")

        for e in self.errors:
            if not isinstance(e, ErrorInfo):
                raise TypeError("errors must be a list[ErrorInfo]")

        if self.ok and len(self.errors) != 0:
            raise ValueError("ok=True results must have errors=[]")
        if (not self.ok) and len(self.errors) == 0:
            raise ValueError("ok=False results must include at least one ErrorInfo")

    def _base_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "correlation_id": self.correlation_id,
            "errors": [e.to_dict() for e in self.errors],
        }

    def to_dict(self) -> dict[str, Any]:
        return self._base_dict()


@dataclass(kw_only=True)
class ActionResult(ResultBase):
    """
    Represents execution that touches the world (devices/APIs).
    """
    action_type: str
    target: dict[str, Any]
    effects: dict[str, Any]

    kind: Literal["action"] = field(init=False, default="action")

    def __post_init__(self) -> None:
        super().__post_init__()
        self.action_type = _require_str(self.action_type, field_name="action_type")
        self.target = _require_dict(self.target, field_name="target")
        self.effects = _require_dict(self.effects, field_name="effects")

    def to_dict(self) -> dict[str, Any]:
        d = self._base_dict()
        d.update(
            {
                "action_type": self.action_type,
                "target": self.target,
                "effects": self.effects,
            }
        )
        return d


@dataclass(kw_only=True)
class ArtifactResult(ResultBase):
    """
    Represents durable artifacts produced by a module/pipeline.
    """
    artifact_type: str
    artifacts: dict[str, str]
    metadata: dict[str, Any]

    kind: Literal["artifact"] = field(init=False, default="artifact")

    def __post_init__(self) -> None:
        super().__post_init__()
        self.artifact_type = _require_str(self.artifact_type, field_name="artifact_type")

        if not isinstance(self.artifacts, dict):
            raise TypeError("artifacts must be a dict[str,str]")
        for k, v in self.artifacts.items():
            if not isinstance(k, str) or k.strip() == "":
                raise ValueError("artifacts keys must be non-empty str")
            if not isinstance(v, str) or v.strip() == "":
                raise ValueError("artifacts values must be non-empty str (relative paths)")
            # Enforce storage-relative safe paths (no leading /, no ..)
            validate_rel_path(v, allow_empty=False)

        self.metadata = _require_dict(self.metadata, field_name="metadata")

    def to_dict(self) -> dict[str, Any]:
        d = self._base_dict()
        d.update(
            {
                "artifact_type": self.artifact_type,
                "artifacts": self.artifacts,
                "metadata": self.metadata,
            }
        )
        return d


@dataclass(kw_only=True)
class ErrorResult(ResultBase):
    """
    Represents an explicit failure not tied to a specific action/artifact object.
    """
    kind: Literal["error"] = field(init=False, default="error")

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.ok is True:
            raise ValueError("ErrorResult must have ok=False")


Result: TypeAlias = ActionResult | ArtifactResult | ErrorResult


def ok_action(
    action_type: str,
    target: dict[str, Any] | None = None,
    effects: dict[str, Any] | None = None,
    *,
    started_at: str | None = None,
    ended_at: str | None = None,
    correlation_id: str | None = None,
) -> ActionResult:
    return ActionResult(
        ok=True,
        started_at=started_at,
        ended_at=ended_at,
        correlation_id=correlation_id,
        errors=[],
        action_type=action_type,
        target=target or {},
        effects=effects or {},
    )


def ok_artifact(
    artifact_type: str,
    artifacts: dict[str, str],
    metadata: dict[str, Any] | None = None,
    *,
    started_at: str | None = None,
    ended_at: str | None = None,
    correlation_id: str | None = None,
) -> ArtifactResult:
    return ArtifactResult(
        ok=True,
        started_at=started_at,
        ended_at=ended_at,
        correlation_id=correlation_id,
        errors=[],
        artifact_type=artifact_type,
        artifacts=artifacts,
        metadata=metadata or {},
    )


def err(
    code: str,
    message: str,
    *,
    correlation_id: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    **detail: Any,
) -> ErrorResult:
    info = ErrorInfo(code=code, message=message, detail=dict(detail))
    return ErrorResult(
        ok=False,
        started_at=started_at,
        ended_at=ended_at,
        correlation_id=correlation_id,
        errors=[info],
    )


def from_dict(d: dict[str, Any]) -> Result:
    if not isinstance(d, dict):
        raise TypeError("from_dict expects a dict")

    kind = d.get("kind")
    if kind not in ("action", "artifact", "error"):
        raise ValueError("result dict must include valid 'kind'")

    ok = d.get("ok")
    if not isinstance(ok, bool):
        raise TypeError("result dict must include bool 'ok'")

    started_at = d.get("started_at", None)
    ended_at = d.get("ended_at", None)
    correlation_id = d.get("correlation_id", None)

    raw_errors = d.get("errors", [])
    if raw_errors is None:
        raw_errors = []
    if not isinstance(raw_errors, list):
        raise TypeError("'errors' must be a list")
    errors = [ErrorInfo.from_dict(e) for e in raw_errors]

    if kind == "action":
        return ActionResult(
            ok=ok,
            started_at=started_at,
            ended_at=ended_at,
            correlation_id=correlation_id,
            errors=errors,
            action_type=d["action_type"],
            target=d["target"],
            effects=d["effects"],
        )

    if kind == "artifact":
        return ArtifactResult(
            ok=ok,
            started_at=started_at,
            ended_at=ended_at,
            correlation_id=correlation_id,
            errors=errors,
            artifact_type=d["artifact_type"],
            artifacts=d["artifacts"],
            metadata=d.get("metadata", {}) or {},
        )

    return ErrorResult(
        ok=ok,
        started_at=started_at,
        ended_at=ended_at,
        correlation_id=correlation_id,
        errors=errors,
    )
