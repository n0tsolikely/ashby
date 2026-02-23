from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import UploadFile

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import load_manifest
from ashby.modules.meetings.schemas.plan import AttachmentMeta
from ashby.modules.meetings.store import add_contribution


def _infer_kind(mime_type: str, filename: str) -> str:
    mt = (mime_type or "").lower()
    fn = (filename or "").lower()
    if mt.startswith("video/") or fn.endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
        return "video"
    return "audio"


async def store_upload(session_id: str, file: UploadFile) -> Tuple[str, AttachmentMeta]:
    """Persist upload as a contribution and return (contribution_id, attachment_meta)."""
    lay = init_stuart_root()

    tmp_dir = lay.root / "tmp" / "web_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "upload.bin"
    tmp_path = tmp_dir / filename

    # Stream to disk (avoid loading large files into memory).
    sha = hashlib.sha256()
    size = 0
    with tmp_path.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            sha.update(chunk)
            size += len(chunk)

    kind = _infer_kind(file.content_type or "", filename)
    contribution_id = add_contribution(session_id=session_id, source_path=tmp_path, source_kind=kind)

    # load manifest to get canonical sha + filename (truth)
    man_path = lay.contributions / contribution_id / "contribution.json"
    m = load_manifest(man_path)

    meta = AttachmentMeta(
        filename=str(m.get("source_filename") or filename),
        mime_type=file.content_type,
        size_bytes=int(size) if size else None,
        sha256=str(m.get("source_sha256") or sha.hexdigest()),
    )

    return contribution_id, meta


async def store_upload_bytes(
    session_id: str,
    filename: str,
    data: bytes,
    mime_type: Optional[str] = None,
) -> Tuple[str, AttachmentMeta]:
    """Persist upload bytes as a contribution and return (contribution_id, attachment_meta).

    This exists so the web door can accept uploads in environments where
    `python-multipart` is not installed (i.e., no multipart/form-data parsing).

    NOTE: This reads the entire body in-memory. For large files, prefer `store_upload()`
    with a real multipart upload.
    """

    lay = init_stuart_root()

    tmp_dir = lay.root / "tmp" / "web_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    safe_name = (filename or "upload.bin").strip() or "upload.bin"
    tmp_path = tmp_dir / safe_name

    sha = hashlib.sha256()
    sha.update(data or b"")
    tmp_path.write_bytes(data or b"")

    kind = _infer_kind(mime_type or "", safe_name)
    contribution_id = add_contribution(session_id=session_id, source_path=tmp_path, source_kind=kind)

    man_path = lay.contributions / contribution_id / "contribution.json"
    m = load_manifest(man_path)

    meta = AttachmentMeta(
        filename=str(m.get("source_filename") or safe_name),
        mime_type=mime_type,
        size_bytes=len(data) if data is not None else None,
        sha256=str(m.get("source_sha256") or sha.hexdigest()),
    )

    return contribution_id, meta
