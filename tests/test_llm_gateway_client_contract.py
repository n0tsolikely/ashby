from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import httpx
import pytest

from ashby.modules.llm.http_gateway import HTTPGatewayLLMService
from ashby.modules.llm.service import LLMFormalizeRequest


def test_gateway_client_posts_expected_payload() -> None:
    seen: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "version": 1,
                "request_id": "req_123",
                "output_json": {"ok": True},
                "evidence_map": {"anchors": []},
                "usage": {"total_tokens": 12},
                "timing_ms": 55,
                "provider": "gemini",
                "model": "gemini-2.5-pro",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    svc = HTTPGatewayLLMService(base_url="http://gateway.local", client=client)
    req = LLMFormalizeRequest(
        transcript_text="hello world",
        mode="meeting",
        template_id="default",
        retention="MED",
        profile="HYBRID",
    )

    res = svc.formalize(req)

    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/formalize"
    assert seen["json"] == {
        "transcript_text": "hello world",
        "mode": "meeting",
        "template_id": "default",
        "retention": "MED",
        "profile": "HYBRID",
    }
    assert res.version == 1
    assert res.request_id == "req_123"
    assert res.output_json == {"ok": True}


def test_gateway_client_rejects_non_v1_and_writes_failure_receipt(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "version": 2,
                "request_id": "req_bad",
                "output_json": {"ok": True},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    svc = HTTPGatewayLLMService(base_url="http://gateway.local", client=client)
    req = LLMFormalizeRequest(
        transcript_text="hello world",
        mode="meeting",
        template_id="default",
        retention="MED",
        profile="HYBRID",
    )

    with pytest.raises(ValueError, match="version must be 1"):
        svc.formalize(req, artifacts_dir=tmp_path)

    receipt = tmp_path / "llm_gateway_failure.json"
    assert receipt.exists()
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["error"] == "gateway_invalid_version"
    assert payload["status_code"] == 200
    assert '"version":2' in payload["raw_body"].replace(" ", "")


def test_gateway_client_502_writes_failure_receipt(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=502, text="bad gateway")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    svc = HTTPGatewayLLMService(base_url="http://gateway.local", client=client)
    req = LLMFormalizeRequest(
        transcript_text="hello world",
        mode="meeting",
        template_id="default",
        retention="MED",
        profile="HYBRID",
    )

    with pytest.raises(RuntimeError, match="Gateway HTTP request failed"):
        svc.formalize(req, artifacts_dir=tmp_path)

    receipt = tmp_path / "llm_gateway_failure.json"
    assert receipt.exists()
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["error"] == "gateway_http_error"
    assert payload["status_code"] == 502
