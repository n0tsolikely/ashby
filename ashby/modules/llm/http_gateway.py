from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from ashby.modules.llm.service import LLMChatRequest, LLMChatResponse, LLMFormalizeRequest, LLMFormalizeResponse
from ashby.modules.meetings.observability import events as obs_events

_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8787"
_ENV_GATEWAY_URL = "STUART_LLM_GATEWAY_URL"


def _gateway_base_url() -> str:
    return (os.environ.get(_ENV_GATEWAY_URL) or _DEFAULT_GATEWAY_URL).strip()


def _write_gateway_failure(
    artifacts_dir: Optional[Path],
    *,
    error: str,
    status_code: Optional[int],
    raw_body: str,
    detail: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    if artifacts_dir is None:
        return None
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = artifacts_dir / "llm_gateway_failure.json"
    payload: Dict[str, Any] = {
        "stage": "llm_gateway",
        "error": error,
        "status_code": status_code,
        "raw_body": raw_body,
        "created_ts": time.time(),
    }
    if detail:
        payload["detail"] = detail
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out


class HTTPGatewayLLMService:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: float = 30.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._base_url = (base_url or _gateway_base_url()).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def health(self) -> Dict[str, Any]:
        response = self._client.get(f"{self._base_url}/health")
        response.raise_for_status()
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise ValueError("Gateway /health must return a JSON object")
        return parsed

    def formalize(self, request: LLMFormalizeRequest, *, artifacts_dir: Optional[Path] = None) -> LLMFormalizeResponse:
        payload = request.to_payload()
        raw_body = ""
        status_code: Optional[int] = None
        run_id = artifacts_dir.parent.name if artifacts_dir is not None and artifacts_dir.parent is not None else None
        cid = f"llm:{run_id}" if run_id else str(uuid.uuid4())
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="llm",
            event="llm.call",
            summary="Calling LLM formalize gateway",
            correlation_id=cid,
            session_id=None,
            run_id=run_id,
            trace_id=cid,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"provider": "http_gateway", "model": "formalize"},
        )

        try:
            response = self._client.post(f"{self._base_url}/v1/formalize", json=payload)
            status_code = response.status_code
            raw_body = response.text
            response.raise_for_status()
        except Exception as exc:
            obs_events.emit_event(
                level="ERROR",
                source="backend",
                component="llm",
                event="llm.error",
                summary="LLM formalize gateway call failed",
                correlation_id=cid,
                session_id=None,
                run_id=run_id,
                trace_id=cid,
                span_id=str(uuid.uuid4()),
                parent_span_id=None,
                data={"status_code": status_code, "reason": f"{type(exc).__name__}: {exc}"},
            )
            obs_events.emit_alert(
                level="ERROR",
                source="backend",
                component="llm",
                event="alert.llm_error",
                summary="LLM formalize gateway call failed",
                correlation_id=cid,
                session_id=None,
                run_id=run_id,
                trace_id=cid,
                span_id=str(uuid.uuid4()),
                parent_span_id=None,
                data={"status_code": status_code},
            )
            fail = _write_gateway_failure(
                artifacts_dir,
                error="gateway_http_error",
                status_code=status_code,
                raw_body=raw_body,
                detail={"exception": f"{type(exc).__name__}: {exc}"},
            )
            suffix = f"; receipt={fail}" if fail else ""
            raise RuntimeError(f"Gateway HTTP request failed{suffix}") from exc

        try:
            parsed = response.json()
        except Exception as exc:
            fail = _write_gateway_failure(
                artifacts_dir,
                error="gateway_non_json_response",
                status_code=status_code,
                raw_body=raw_body,
                detail={"exception": f"{type(exc).__name__}: {exc}"},
            )
            suffix = f"; receipt={fail}" if fail else ""
            raise ValueError(f"Gateway returned non-JSON response{suffix}") from exc

        if not isinstance(parsed, dict):
            fail = _write_gateway_failure(
                artifacts_dir,
                error="gateway_json_not_object",
                status_code=status_code,
                raw_body=raw_body,
            )
            suffix = f"; receipt={fail}" if fail else ""
            raise ValueError(f"Gateway JSON response is not an object{suffix}")

        version = parsed.get("version")
        if version != 1:
            fail = _write_gateway_failure(
                artifacts_dir,
                error="gateway_invalid_version",
                status_code=status_code,
                raw_body=raw_body,
                detail={"version": version},
            )
            suffix = f"; receipt={fail}" if fail else ""
            raise ValueError(f"Gateway response version must be 1; got {version!r}{suffix}")

        request_id = str(parsed.get("request_id") or "")
        output_json = parsed.get("output_json")
        if not request_id:
            raise ValueError("Gateway response missing request_id")
        if not isinstance(output_json, dict):
            raise ValueError("Gateway response missing output_json object")

        evidence_map = parsed.get("evidence_map")
        usage = parsed.get("usage")
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="llm",
            event="llm.response",
            summary="LLM formalize gateway response received",
            correlation_id=cid,
            session_id=None,
            run_id=run_id,
            trace_id=cid,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={
                "provider": str(parsed.get("provider") or ""),
                "model": str(parsed.get("model") or ""),
                "status_code": int(status_code or 200),
                "timing_ms": int(parsed.get("timing_ms") or 0),
                "usage": usage if isinstance(usage, dict) else {},
            },
        )
        return LLMFormalizeResponse(
            version=1,
            request_id=request_id,
            output_json=output_json,
            evidence_map=evidence_map if isinstance(evidence_map, dict) else {},
            usage=usage if isinstance(usage, dict) else {},
            timing_ms=int(parsed.get("timing_ms") or 0),
            provider=str(parsed.get("provider") or ""),
            model=str(parsed.get("model") or ""),
        )

    def chat(self, request: LLMChatRequest, *, artifacts_dir: Optional[Path] = None) -> LLMChatResponse:
        payload = request.to_payload()
        raw_body = ""
        status_code: Optional[int] = None
        ui_state = payload.get("ui_state") if isinstance(payload.get("ui_state"), dict) else {}
        session_id = str(ui_state.get("selected_session_id") or "").strip() or None
        cid = str(ui_state.get("correlation_id") or "").strip() or str(uuid.uuid4())
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="llm",
            event="llm.call",
            summary="Calling LLM chat gateway",
            correlation_id=cid,
            session_id=session_id,
            run_id=None,
            trace_id=cid,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"provider": "http_gateway", "model": "chat"},
        )

        try:
            response = self._client.post(f"{self._base_url}/v1/chat", json=payload)
            status_code = response.status_code
            raw_body = response.text
            response.raise_for_status()
        except Exception as exc:
            obs_events.emit_event(
                level="ERROR",
                source="backend",
                component="llm",
                event="llm.error",
                summary="LLM chat gateway call failed",
                correlation_id=cid,
                session_id=session_id,
                run_id=None,
                trace_id=cid,
                span_id=str(uuid.uuid4()),
                parent_span_id=None,
                data={"status_code": status_code, "reason": f"{type(exc).__name__}: {exc}"},
            )
            obs_events.emit_alert(
                level="ERROR",
                source="backend",
                component="llm",
                event="alert.llm_error",
                summary="LLM chat gateway call failed",
                correlation_id=cid,
                session_id=session_id,
                run_id=None,
                trace_id=cid,
                span_id=str(uuid.uuid4()),
                parent_span_id=None,
                data={"status_code": status_code},
            )
            fail = _write_gateway_failure(
                artifacts_dir,
                error="gateway_http_error",
                status_code=status_code,
                raw_body=raw_body,
                detail={"exception": f"{type(exc).__name__}: {exc}"},
            )
            suffix = f"; receipt={fail}" if fail else ""
            raise RuntimeError(f"Gateway HTTP request failed{suffix}") from exc

        try:
            parsed = response.json()
        except Exception as exc:
            fail = _write_gateway_failure(
                artifacts_dir,
                error="gateway_non_json_response",
                status_code=status_code,
                raw_body=raw_body,
                detail={"exception": f"{type(exc).__name__}: {exc}"},
            )
            suffix = f"; receipt={fail}" if fail else ""
            raise ValueError(f"Gateway returned non-JSON response{suffix}") from exc

        if not isinstance(parsed, dict):
            fail = _write_gateway_failure(
                artifacts_dir,
                error="gateway_json_not_object",
                status_code=status_code,
                raw_body=raw_body,
            )
            suffix = f"; receipt={fail}" if fail else ""
            raise ValueError(f"Gateway JSON response is not an object{suffix}")

        version = parsed.get("version")
        if version != 1:
            fail = _write_gateway_failure(
                artifacts_dir,
                error="gateway_invalid_version",
                status_code=status_code,
                raw_body=raw_body,
                detail={"version": version},
            )
            suffix = f"; receipt={fail}" if fail else ""
            raise ValueError(f"Gateway response version must be 1; got {version!r}{suffix}")

        request_id = str(parsed.get("request_id") or "")
        output_json = parsed.get("output_json")
        if not request_id:
            raise ValueError("Gateway response missing request_id")
        if not isinstance(output_json, dict):
            raise ValueError("Gateway response missing output_json object")

        usage = parsed.get("usage")
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="llm",
            event="llm.response",
            summary="LLM chat gateway response received",
            correlation_id=cid,
            session_id=session_id,
            run_id=None,
            trace_id=cid,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={
                "provider": str(parsed.get("provider") or ""),
                "model": str(parsed.get("model") or ""),
                "status_code": int(status_code or 200),
                "timing_ms": int(parsed.get("timing_ms") or 0),
                "usage": usage if isinstance(usage, dict) else {},
            },
        )
        return LLMChatResponse(
            version=1,
            request_id=request_id,
            output_json=output_json,
            usage=usage if isinstance(usage, dict) else {},
            timing_ms=int(parsed.get("timing_ms") or 0),
            provider=str(parsed.get("provider") or ""),
            model=str(parsed.get("model") or ""),
        )
