from __future__ import annotations

import os
import uuid

from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse


def request_id() -> str:
    return uuid.uuid4().hex[:12]


def trace_payload(req_id: Optional[str] = None) -> Dict[str, Any]:
    return {"request_id": req_id or request_id()}


def ok(payload: Optional[Dict[str, Any]] = None, *, req_id: Optional[str] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"ok": True, "trace": trace_payload(req_id)}
    if payload:
        body.update(payload)
    return body


def fail(
    code: str,
    message: str,
    *,
    status: int,
    details: Optional[Dict[str, Any]] = None,
    req_id: Optional[str] = None,
) -> JSONResponse:
    err: Dict[str, Any] = {"code": code, "message": message}
    if details is not None and str(os.getenv("STUART_DEBUG", "")).strip() == "1":
        err["details"] = details
    return JSONResponse(
        status_code=int(status),
        content={"ok": False, "error": err, "trace": trace_payload(req_id)},
    )
