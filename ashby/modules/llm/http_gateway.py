from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from ashby.modules.llm.service import LLMFormalizeRequest, LLMFormalizeResponse

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

        try:
            response = self._client.post(f"{self._base_url}/v1/formalize", json=payload)
            status_code = response.status_code
            raw_body = response.text
            response.raise_for_status()
        except Exception as exc:
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
