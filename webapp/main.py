from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import os

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ashby.interfaces.web.uploads import store_upload
from ashby.modules.meetings.clarify_or_preview import clarify_or_preview
from ashby.modules.meetings.mode_registry import validate_mode
from ashby.modules.meetings.schemas.plan import SessionContext, AttachmentMeta
from ashby.modules.meetings.schemas.run_request import RunRequest
from ashby.modules.meetings.store import create_session


app = FastAPI()

BASE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _stuart_root() -> Path:
    # For download sandboxing / path validation only. The Meetings module uses STUART_ROOT.
    sr = os.environ.get("STUART_ROOT") or os.environ.get("ASHBY_STUART_ROOT")
    if sr:
        return Path(sr)
    return Path.home() / "ashby_runtime" / "stuart"


def _safe_resolve_under(root: Path, p: Path) -> Path:
    root_r = root.resolve()
    p_r = p.resolve()
    if root_r not in p_r.parents and p_r != root_r:
        raise ValueError("path escapes root")
    return p_r


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "mode": "Meeting",
            "template": "Default",
        },
    )


@app.post("/upload")
async def upload(file: UploadFile = File(...), mode: str = "meeting"):
    """Upload-only path (QUEST_062).

    Policy rail: Upload ≠ process.
    This endpoint only stores a contribution + returns a plan preview.
    The actual run/processing will be triggered by a later confirm gate (QUEST_063).
    """

    mv = validate_mode(mode)
    if not mv.ok or mv.canonical is None:
        return JSONResponse(status_code=400, content={"error": mv.message or "invalid mode"})

    # Create a new session per upload (scaffold behavior).
    session_id = create_session(mode=mv.canonical, title=None)

    # Store the upload as a contribution (immutable). No run created here.
    con_id, meta = await store_upload(session_id=session_id, file=file)

    # Deterministic plan preview (no execution).
    rr = RunRequest(mode=mv.canonical)
    session_ctx = SessionContext(active_session_id=session_id, last_run_id=None)
    preview_out = clarify_or_preview(
        text="formalize",
        attachments=[meta],
        run_request=rr,
        session=session_ctx,
        door="web",
    )

    return JSONResponse(
        {
            "ok": True,
            "session_id": session_id,
            "contribution_id": con_id,
            "attachment": asdict(meta),
            "plan_preview": asdict(preview_out.preview) if preview_out.preview else None,
            "needs_clarification": bool(preview_out.needs_clarification),
            "clarify": asdict(preview_out.clarify) if preview_out.clarify else None,
        }
    )


@app.get("/download")
async def download(path: str):
    # NOTE: This scaffold download path is retained for legacy testing/manual use.
    # In the v1 web door, downloads are served from /download/{run_id}/{filename}.
    if not path:
        raise HTTPException(status_code=400, detail="missing path")
    sr = _stuart_root()
    try:
        p = _safe_resolve_under(sr, Path(path))
    except Exception:
        raise HTTPException(status_code=403, detail="invalid path")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return Response(
        content=p.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{p.name}"'},
    )
