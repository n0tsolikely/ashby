from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ashby.interfaces.web.registry_api import registry_payload
from ashby.interfaces.web.sessions import list_sessions, create_session
from ashby.interfaces.web.uploads import store_upload
from ashby.interfaces.web.runs import list_run_artifacts, artifact_response

from ashby.modules.meetings.clarify_or_preview import clarify_or_preview
from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.store import create_run, get_run_state
from ashby.modules.meetings.schemas.plan import UIState, SessionContext, AttachmentMeta

from ashby.modules.meetings.index import sqlite_fts


def create_app() -> FastAPI:
    app = FastAPI(title="Stuart Web Door", version="0.3")

    base_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Any:
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/api/registry")
    def api_registry() -> Dict[str, Any]:
        return registry_payload()

    @app.get("/api/sessions")
    def api_sessions(limit: int = 50) -> Dict[str, Any]:
        return {"sessions": list_sessions(limit=limit)}

    @app.post("/api/sessions")
    async def api_create_session(payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = (payload.get("mode") or "").strip().lower()
        title = payload.get("title") or None
        if not mode:
            return JSONResponse(status_code=400, content={"error": "mode is required"})
        sid = create_session(mode=mode, title=title)
        return {"session_id": sid}

    @app.post("/api/upload")
    async def api_upload(session_id: str, file: UploadFile = File(...)) -> Dict[str, Any]:
        """Upload media -> store as contribution. Returns attachment meta for planning."""
        if not session_id:
            return JSONResponse(status_code=400, content={"error": "session_id is required"})
        con_id, meta = await store_upload(session_id=session_id, file=file)
        return {"ok": True, "contribution_id": con_id, "attachment": asdict(meta)}

    @app.post("/api/message")
    async def api_message(payload: Dict[str, Any]) -> Dict[str, Any]:
        text = (payload.get("text") or "")
        session_id = payload.get("session_id")
        ui_raw = payload.get("ui") or {}
        attachments_raw = payload.get("attachments") or []

        ui = UIState(
            mode=ui_raw.get("mode"),
            template=ui_raw.get("template"),
            speakers=ui_raw.get("speakers"),
        )

        attachments: Optional[list[AttachmentMeta]] = None
        if isinstance(attachments_raw, list) and attachments_raw:
            tmp = []
            for a in attachments_raw:
                if isinstance(a, dict):
                    tmp.append(
                        AttachmentMeta(
                            filename=str(a.get("filename") or ""),
                            mime_type=a.get("mime_type"),
                            size_bytes=a.get("size_bytes"),
                            sha256=a.get("sha256"),
                        )
                    )
            attachments = tmp

        session = SessionContext(active_session_id=session_id, last_run_id=None)

        out = clarify_or_preview(
            text=text,
            attachments=attachments,
            ui=ui,
            session=session,
            door="web",
        )
        return {"result": asdict(out)}

    @app.post("/api/run")
    async def api_run(payload: Dict[str, Any], background: BackgroundTasks) -> Dict[str, Any]:
        """Create a run and execute it asynchronously (UI polls status)."""
        session_id = payload.get("session_id")
        ui_raw = payload.get("ui") or {}
        if not isinstance(session_id, str) or not session_id:
            return JSONResponse(status_code=400, content={"error": "session_id is required"})

        mode = (ui_raw.get("mode") or "").strip().lower()
        template = (ui_raw.get("template") or "default").strip().lower() or "default"
        speakers = ui_raw.get("speakers")

        if not mode:
            return JSONResponse(status_code=400, content={"error": "mode is required to run"})

        plan = {"steps": [{"kind": "formalize", "params": {"mode": mode, "template": template, "speakers": speakers}}]}
        run_id = create_run(session_id=session_id, plan=plan)

        # Run in background so the UI can poll progress.
        background.add_task(run_job, run_id)

        state = get_run_state(run_id)
        return {"ok": True, "run_id": run_id, "state": state}

    @app.get("/api/runs/{run_id}")
    def api_run_status(run_id: str) -> Dict[str, Any]:
        state = get_run_state(run_id)
        return {"run_id": run_id, "state": state, "artifacts": list_run_artifacts(run_id)}

    @app.get("/download/{run_id}/{filename}")
    def download_artifact(run_id: str, filename: str) -> Any:
        return artifact_response(run_id, filename)

    @app.get("/api/search")
    def api_search(q: str, session_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        db_path = sqlite_fts.get_db_path()
        conn = sqlite_fts.connect(db_path)
        try:
            hits = sqlite_fts.search(conn, q, limit=int(limit), session_id=session_id)
            return {"ok": True, "hits": [asdict(h) for h in hits]}
        finally:
            conn.close()

    return app


app = create_app()
