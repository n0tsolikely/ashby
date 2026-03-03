from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ashby.interfaces.llm_gateway.providers import GeminiProvider
from ashby.interfaces.llm_gateway.schemas import (
    ChatGatewayRequest,
    ChatGatewayResponse,
    ErrorResponse,
    FormalizeRequest,
    FormalizeResponse,
)
from ashby.interfaces.llm_gateway.validate import (
    validate_chat_output,
    validate_chat_request,
    validate_formalization_output,
    validate_formalization_request,
)


logger = logging.getLogger("ashby.llm_gateway")


def _request_id() -> str:
    return uuid.uuid4().hex


def _provider_from_env() -> Any:
    provider = (os.environ.get("LLM_GATEWAY_PROVIDER") or "gemini").strip().lower()
    if provider != "gemini":
        raise RuntimeError(f"Unsupported LLM_GATEWAY_PROVIDER: {provider}")
    return GeminiProvider()


def _error_body(*, request_id: str, code: str, message: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    body = ErrorResponse(
        request_id=request_id,
        error={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )
    return body.model_dump()


def create_app() -> FastAPI:
    app = FastAPI(title="Ashby LLM Gateway", version="1")

    def _get_provider() -> Any:
        provider = getattr(app.state, "provider", None)
        if provider is None:
            provider = _provider_from_env()
            app.state.provider = provider
            logger.info("llm_gateway_startup provider=%s model=%s", provider.provider_name, provider.model)
        return provider

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = _request_id()
        return JSONResponse(
            status_code=422,
            content=_error_body(
                request_id=req_id,
                code="request_validation_error",
                message="Invalid request payload",
                details={"errors": exc.errors()},
            ),
        )

    @app.get("/health")
    async def health() -> JSONResponse:
        try:
            provider = _get_provider()
        except Exception as e:
            req_id = _request_id()
            return JSONResponse(
                status_code=503,
                content=_error_body(
                    request_id=req_id,
                    code="startup_error",
                    message=str(e),
                ),
            )
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "version": 1,
                "provider": provider.provider_name,
                "model": provider.model,
            },
        )

    @app.post("/v1/formalize")
    async def formalize(req: FormalizeRequest) -> JSONResponse:
        request_id = _request_id()
        started = time.time()
        try:
            validate_formalization_request(req)
            provider = _get_provider()
            provider_out = provider.formalize(req)
            if not isinstance(provider_out, dict):
                raise ValueError("provider response must be object")
            raw_output_json = provider_out.get("output_json")
            if not isinstance(raw_output_json, dict):
                raise ValueError("provider output_json missing or invalid")
            output_json = validate_formalization_output(request=req, request_id=request_id, output_json=raw_output_json)
            evidence_map = provider_out.get("evidence_map")
            usage = provider_out.get("usage")
            elapsed_ms = int((time.time() - started) * 1000)

            usage_payload = usage if isinstance(usage, dict) else {}
            logger.info(
                "formalize_ok request_id=%s timing_ms=%s usage=%s",
                request_id,
                elapsed_ms,
                usage_payload,
            )
            resp = FormalizeResponse(
                request_id=request_id,
                output_json=output_json,
                evidence_map=evidence_map if isinstance(evidence_map, dict) else {},
                usage=usage_payload,
                timing_ms=elapsed_ms,
                provider=provider.provider_name,
                model=provider.model,
            )
            return JSONResponse(status_code=200, content=resp.model_dump())
        except ValueError as e:
            elapsed_ms = int((time.time() - started) * 1000)
            logger.warning("formalize_schema_error request_id=%s timing_ms=%s error=%s", request_id, elapsed_ms, str(e))
            return JSONResponse(
                status_code=422,
                content=_error_body(
                    request_id=request_id,
                    code="validation_failed",
                    message=str(e),
                    details={"error": str(e)},
                ),
            )
        except Exception as e:
            elapsed_ms = int((time.time() - started) * 1000)
            logger.exception("formalize_provider_error request_id=%s timing_ms=%s", request_id, elapsed_ms)
            return JSONResponse(
                status_code=502,
                content=_error_body(
                    request_id=request_id,
                    code="provider_error",
                    message="Provider call failed",
                    details={"error": f"{type(e).__name__}: {e}"},
                ),
            )

    @app.post("/v1/chat")
    async def chat(req: ChatGatewayRequest) -> JSONResponse:
        request_id = _request_id()
        started = time.time()
        try:
            validate_chat_request(req)
            provider = _get_provider()
            provider_out = provider.chat(req)
            if not isinstance(provider_out, dict):
                raise ValueError("provider response must be object")
            raw_output_json = provider_out.get("output_json")
            if not isinstance(raw_output_json, dict):
                raise ValueError("provider output_json missing or invalid")
            output_json = validate_chat_output(request_id=request_id, output_json=raw_output_json)
            usage = provider_out.get("usage")
            elapsed_ms = int((time.time() - started) * 1000)
            usage_payload = usage if isinstance(usage, dict) else {}
            logger.info("chat_ok request_id=%s timing_ms=%s usage=%s", request_id, elapsed_ms, usage_payload)
            resp = ChatGatewayResponse(
                request_id=request_id,
                output_json=output_json,
                usage=usage_payload,
                timing_ms=elapsed_ms,
                provider=provider.provider_name,
                model=provider.model,
            )
            return JSONResponse(status_code=200, content=resp.model_dump())
        except ValueError as e:
            elapsed_ms = int((time.time() - started) * 1000)
            logger.warning("chat_schema_error request_id=%s timing_ms=%s error=%s", request_id, elapsed_ms, str(e))
            return JSONResponse(
                status_code=422,
                content=_error_body(
                    request_id=request_id,
                    code="validation_failed",
                    message=str(e),
                    details={"error": str(e)},
                ),
            )
        except Exception as e:
            elapsed_ms = int((time.time() - started) * 1000)
            logger.exception("chat_provider_error request_id=%s timing_ms=%s", request_id, elapsed_ms)
            return JSONResponse(
                status_code=502,
                content=_error_body(
                    request_id=request_id,
                    code="provider_error",
                    message="Provider call failed",
                    details={"error": f"{type(e).__name__}: {e}"},
                ),
            )

    return app


app = create_app()


def main() -> int:
    import uvicorn

    port_raw = (os.environ.get("LLM_GATEWAY_PORT") or "8787").strip()
    port = int(port_raw)
    uvicorn.run("ashby.interfaces.llm_gateway.app:app", host="127.0.0.1", port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
