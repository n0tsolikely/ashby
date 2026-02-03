from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import os

from ashby.interfaces.telegram.stuart_runner import run_default_pipeline

app = FastAPI()

BASE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

def _stuart_root() -> Path:
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
    return templates.TemplateResponse("index.html", {
        "request": request,
        "mode": "Meeting",
        "template": "Default"
    })

@app.post("/upload")
async def upload(file: UploadFile = File(...), mode: str = "meeting", source_kind: str = "audio"):
    sr = _stuart_root()
    inbox = sr / "inbox" / "webapp"
    inbox.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = (file.filename or "upload.bin").replace("/", "_").replace("\\", "_")
    dest = inbox / f"{ts}__{safe_name}"

    data = await file.read()
    dest.write_bytes(data)

    out = run_default_pipeline(local_path=str(dest), source_kind=source_kind, mode=mode, template="default")
    rn = out.get("run") or {}
    run_id = rn.get("run_id") if isinstance(rn, dict) else None

    pdf_path = out.get("pdf_path")
    pdf_url = None
    if isinstance(pdf_path, str) and pdf_path:
        pdf_url = "/download?path=" + pdf_path

    return JSONResponse({
        "ok": True,
        "filename": safe_name,
        "run_id": run_id,
        "pdf_path": pdf_path,
        "pdf_url": pdf_url,
    })

@app.get("/download")
async def download(path: str):
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
