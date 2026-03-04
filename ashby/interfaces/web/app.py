from __future__ import annotations

import json
import shutil
import time
import hashlib
import threading
import os
import uuid

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ashby.interfaces.web.registry_api import registry_payload
from ashby.interfaces.web.templates_api import router as templates_router
from ashby.interfaces.web.sessions import list_sessions, create_session
from ashby.interfaces.web.uploads import store_upload, store_upload_bytes
from ashby.interfaces.web.runs import list_run_artifacts, artifact_response, primary_downloads
from ashby.interfaces.web.http_envelope import ok, fail
from ashby.interfaces.web.transcripts import (
    normalize_segment,
    read_json,
    run_id_from_transcript_version_id,
)

from ashby.modules.meetings.clarify_or_preview import clarify_or_preview
from ashby.modules.meetings.delete_ops import (
    delete_run as delete_run_op,
    delete_session as delete_session_op,
    list_run_dependencies_for_transcript,
)
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import load_manifest
from ashby.modules.meetings.mode_registry import validate_mode
from ashby.modules.meetings.pipeline.job_runner import run_job, poll_progress
from ashby.modules.meetings.router.router import build_intent_and_plan
from ashby.modules.meetings.manifests import save_manifest_atomic_overwrite
from ashby.modules.meetings.store import (
    create_run,
    default_formalization_title,
    get_run_state,
    normalize_formalization_title,
)
from ashby.modules.meetings.overlays import create_speaker_map_overlay, load_speaker_map_overlay
from ashby.modules.meetings.session_state import (
    get_speaker_overlay_for_transcript,
    load_session_state,
    set_speaker_overlay_for_transcript,
    set_active_transcript_version,
)
from ashby.modules.meetings.schemas.plan import SessionContext, AttachmentMeta
from ashby.modules.meetings.schemas.run_request import RunRequest
from ashby.modules.meetings.transcript_versions import (
    delete_transcript_version,
    ensure_legacy_transcript_versions,
    list_transcript_versions,
    load_transcript_version,
    resolve_transcript_version,
)

from ashby.modules.meetings.index import sqlite_fts
from ashby.modules.meetings.index.ingest import refresh_speaker_maps_for_transcript
from ashby.modules.meetings.export.bundle import export_session_bundle
from ashby.modules.meetings.chat import (
    answer_with_evidence,
    handle_command,
    hydrate_evidence,
    parse_command,
    retrieve_hits,
)
from ashby.modules.meetings.schemas.chat import (
    ChatActionJumpToSegmentV1,
    ChatActionOpenSessionV1,
    ChatReplyV1,
    parse_chat_request_v1,
)
from ashby.modules.meetings.observability import events as obs_events


def create_app() -> FastAPI:
    app = FastAPI(title="Stuart Web Door", version="0.3")
    app.include_router(templates_router, prefix="/api")

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        correlation_id = (request.headers.get("X-Correlation-Id") or "").strip() or str(uuid.uuid4())
        trace_id = correlation_id
        span_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        request.state.trace_id = trace_id
        request.state.span_id = span_id
        request.state.parent_span_id = None

        session_id = request.query_params.get("session_id")
        run_id = request.query_params.get("run_id")
        path = request.url.path
        method = request.method.upper()

        started = time.perf_counter()
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="api",
            event="api.request_received",
            summary=f"{method} {path}",
            correlation_id=correlation_id,
            session_id=session_id,
            run_id=run_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            data={"method": method, "path": path},
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            safe_msg = f"{type(exc).__name__}: {exc}"
            obs_events.emit_event(
                level="ERROR",
                source="backend",
                component="api",
                event="api.error",
                summary=f"Unhandled exception during {method} {path}",
                correlation_id=correlation_id,
                session_id=session_id,
                run_id=run_id,
                trace_id=trace_id,
                span_id=str(uuid.uuid4()),
                parent_span_id=span_id,
                duration_ms=duration_ms,
                data={"method": method, "path": path, "error": safe_msg},
            )
            obs_events.emit_alert(
                level="ERROR",
                source="backend",
                component="api",
                event="alert.backend_exception",
                summary=f"Unhandled exception during {method} {path}",
                correlation_id=correlation_id,
                session_id=session_id,
                run_id=run_id,
                trace_id=trace_id,
                span_id=str(uuid.uuid4()),
                parent_span_id=span_id,
                duration_ms=duration_ms,
                data={"method": method, "path": path, "error": safe_msg},
            )
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="api",
            event="api.response_sent",
            summary=f"{method} {path} -> {response.status_code}",
            correlation_id=correlation_id,
            session_id=session_id,
            run_id=run_id,
            trace_id=trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=span_id,
            duration_ms=duration_ms,
            data={"method": method, "path": path, "status_code": int(response.status_code)},
        )
        return response

    @app.on_event("startup")
    async def observability_startup_event() -> None:
        configured = any(
            bool((os.environ.get(k) or "").strip())
            for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        )
        root = obs_events.get_stuart_root()
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="system",
            event="system.start",
            summary="Stuart backend started",
            correlation_id=str(uuid.uuid4()),
            session_id=None,
            run_id=None,
            trace_id="",
            span_id="",
            parent_span_id=None,
            data={
                "logging_enabled": obs_events.is_enabled(),
                "stuart_root": str(root),
                "llm_provider_configured": configured,
                "version": app.version,
            },
        )

    base_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Any:
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/api/registry")
    async def api_registry() -> Dict[str, Any]:
        return ok(registry_payload())

    @app.get("/api/sessions")
    async def api_sessions(
        limit: int = 50, offset: int = 0, q: Optional[str] = None, mode: Optional[str] = None, attendee: Optional[str] = None
    ) -> Dict[str, Any]:
        sessions_all = list_sessions(limit=100000)
        query = (q or "").strip().lower()
        mode_filter = (mode or "").strip().lower()
        attendee_query = (attendee or "").strip()
        attendee_norm = sqlite_fts.normalize_person_name(attendee_query) if attendee_query else ""
        attendee_session_ids: Optional[set[str]] = None

        if attendee_query and attendee_norm:
            lay = init_stuart_root()
            conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=lay.root))
            try:
                sqlite_fts.ensure_schema(conn)
                matched = sqlite_fts.list_sessions_by_attendee(conn, attendee_query)
                candidates = {str(row.session_id) for row in matched}
                filtered: set[str] = set()
                for sid in candidates:
                    st = load_session_state(sid)
                    active_trv = st.get("active_transcript_version_id")
                    if not isinstance(active_trv, str) or not active_trv.strip():
                        continue
                    active_trv = active_trv.strip()
                    try:
                        trv = load_transcript_version(sid, active_trv)
                    except Exception:
                        continue
                    active_run_id = str(trv.get("run_id") or "").strip()
                    if not active_run_id:
                        continue
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM speaker_maps
                        WHERE session_id = ? AND run_id = ? AND speaker_name_norm = ?
                        LIMIT 1;
                        """,
                        (sid, active_run_id, attendee_norm),
                    ).fetchone()
                    if row is not None:
                        filtered.add(sid)
                attendee_session_ids = filtered
            finally:
                conn.close()
        elif attendee_query:
            attendee_session_ids = set()

        rows: list[Dict[str, Any]] = []
        for s in sessions_all:
            sid = str(s.get("session_id") or "")
            if not sid:
                continue
            smode = str(s.get("mode") or "").strip().lower()
            title = s.get("title")
            title_l = str(title or "").lower()
            contrib_count = _session_contribution_count(sid)
            has_audio = contrib_count > 0

            runs = _runs_for_session(sid, limit=200)
            trv_rows = list_transcript_versions(sid)
            run_ids = [str(r.get("run_id") or "").lower() for r in runs if isinstance(r, dict)]
            trv_ids = [str(v.get("transcript_version_id") or "").lower() for v in trv_rows if isinstance(v, dict)]

            match_kinds: list[str] = []
            if query:
                title_match = query in title_l
                id_match = (
                    query in sid.lower()
                    or any(query in rid for rid in run_ids if rid)
                    or any(query in tid for tid in trv_ids if tid)
                )
                if not title_match and not id_match:
                    continue
                if title_match:
                    match_kinds.append("TITLE_MATCH")
                if id_match:
                    match_kinds.append("ID_MATCH")

            if mode_filter and smode != mode_filter:
                continue
            if attendee_session_ids is not None:
                if sid not in attendee_session_ids:
                    continue
                match_kinds.append("ATTENDEE_MATCH")

            latest = runs[0] if runs else None
            has_transcript = any(
                any((a.get("name") in {"transcript.json", "aligned_transcript.json"}) for a in (r.get("artifacts") or []))
                for r in runs
            )
            has_formalization = any(
                bool(((r.get("downloads") or {}).get("primary") or {}).get("md"))
                or bool(((r.get("downloads") or {}).get("primary") or {}).get("txt"))
                or bool(((r.get("downloads") or {}).get("primary") or {}).get("json"))
                or bool(((r.get("downloads") or {}).get("primary") or {}).get("pdf"))
                for r in runs
            )

            rows.append(
                {
                    "session_id": sid,
                    "created_ts": s.get("created_ts"),
                    "mode": s.get("mode"),
                    "title": title,
                    "runs": s.get("runs", []),
                    "contributions": s.get("contributions", []),
                    "contributions_count": contrib_count,
                    "has_audio": has_audio,
                    "latest_run": {
                        "run_id": latest.get("run_id"),
                        "status": latest.get("status"),
                        "stage": latest.get("stage"),
                        "progress": latest.get("progress"),
                        "created_ts": latest.get("created_ts"),
                    }
                    if latest
                    else None,
                    "has_transcript": has_transcript,
                    "has_formalization": has_formalization,
                }
            )
            if query or attendee_query:
                rows[-1]["match_kinds"] = sorted(set(match_kinds))

        rows.sort(key=lambda s: (float(s.get("created_ts") or 0.0), str(s.get("session_id") or "")), reverse=True)
        start = max(int(offset), 0)
        end = start + max(int(limit), 1)
        page_rows = rows[start:end]
        return ok(
            {
                "sessions": page_rows,
                "page": {"limit": int(limit), "offset": int(offset), "returned": len(page_rows), "total": len(rows)},
            }
        )

    def _runs_for_session(session_id: str, limit: int = 200) -> list[Dict[str, Any]]:
        lay = init_stuart_root()
        rows: list[Dict[str, Any]] = []
        if not lay.runs.exists():
            return rows

        for run_dir in lay.runs.iterdir():
            if not run_dir.is_dir():
                continue
            run_json = run_dir / "run.json"
            if not run_json.exists():
                continue
            try:
                state = load_manifest(run_json)
            except Exception:
                continue
            if str(state.get("session_id") or "") != session_id:
                continue

            run_id = str(state.get("run_id") or run_dir.name)
            rows.append(
                {
                    "run_id": run_id,
                    "status": state.get("status"),
                    "stage": state.get("stage"),
                    "progress": state.get("progress"),
                    "created_ts": state.get("created_ts"),
                    "started_ts": state.get("started_ts"),
                    "ended_ts": state.get("ended_ts"),
                    "plan": state.get("plan") or {},
                    "primary_outputs": state.get("primary_outputs") or {},
                    "title_override": state.get("title_override"),
                    "downloads": primary_downloads(run_id, state=state),
                    "artifacts": list_run_artifacts(run_id),
                }
            )

        rows.sort(key=lambda r: float(r.get("created_ts") or 0.0), reverse=True)
        return rows[: max(int(limit), 1)]

    def _read_text(path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None

    def _artifact_path_for_primary(run_id: str, primary_outputs: Dict[str, Any], key: str) -> Optional[Path]:
        ptr = primary_outputs.get(key) if isinstance(primary_outputs, dict) else None
        if not isinstance(ptr, dict):
            return None
        rel = ptr.get("path")
        if not isinstance(rel, str) or not rel.strip():
            return None
        lay = init_stuart_root()
        run_dir = lay.runs / run_id
        candidate = (run_dir / rel).resolve()
        try:
            candidate.relative_to(run_dir.resolve())
        except Exception:
            return None
        return candidate if candidate.exists() else None

    def _first_existing_artifact(run_id: str, names: list[str]) -> Optional[Path]:
        lay = init_stuart_root()
        artifacts_dir = lay.runs / run_id / "artifacts"
        for name in names:
            p = artifacts_dir / name
            if p.exists():
                return p
        return None

    def _spawn_run_job(run_id: str) -> None:
        # Fire-and-forget execution so API calls return immediately and the UI can poll.
        t = threading.Thread(target=run_job, args=(run_id,), daemon=True)
        t.start()

    def _session_contribution_count(session_id: str) -> int:
        lay = init_stuart_root()
        if not lay.contributions.exists():
            return 0
        count = 0
        for con_dir in lay.contributions.iterdir():
            if not con_dir.is_dir():
                continue
            cpath = con_dir / "contribution.json"
            if not cpath.exists():
                continue
            try:
                cm = load_manifest(cpath)
            except Exception:
                continue
            if str(cm.get("session_id") or "") == session_id:
                count += 1
        return count

    @app.get("/api/sessions/{session_id}/runs")
    async def api_session_runs(
        session_id: str,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        include_artifacts: bool = False,
    ) -> Dict[str, Any]:
        rows = _runs_for_session(session_id, limit=100000)
        if status:
            rows = [r for r in rows if str(r.get("status") or "").strip().lower() == str(status).strip().lower()]
        if not include_artifacts:
            rows = [{k: v for k, v in r.items() if k != "artifacts"} for r in rows]
        start = max(int(offset), 0)
        end = start + max(int(limit), 1)
        page_rows = rows[start:end]
        return ok(
            {
                "session_id": session_id,
                "runs": page_rows,
                "page": {"limit": int(limit), "offset": int(offset), "returned": len(page_rows), "total": len(rows)},
            }
        )

    def _normalize_speaker_map_input(mapping_raw: Any) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not isinstance(mapping_raw, dict):
            return out
        for key, value in mapping_raw.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            label = key.strip().upper()
            name = value.strip()
            if not label or not name:
                continue
            out[label] = name
        return out

    def _speaker_map_view_for_transcript(session_id: str, transcript_version_id: str) -> Dict[str, Any]:
        overlay_id = get_speaker_overlay_for_transcript(session_id, transcript_version_id)
        mapping: Dict[str, str] = {}
        if isinstance(overlay_id, str) and overlay_id.strip():
            try:
                mapping = load_speaker_map_overlay(session_id, overlay_id.strip())
                overlay_id = overlay_id.strip()
            except Exception:
                overlay_id = None
                mapping = {}
        else:
            overlay_id = None
        return {"speaker_overlay_id": overlay_id, "speaker_map": mapping}

    def _save_speaker_map_for_transcript(
        *, session_id: str, transcript_version_id: str, mapping_raw: Any, author: str
    ) -> Dict[str, Any]:
        mapping = _normalize_speaker_map_input(mapping_raw)
        overlay = None
        overlay_id = None
        if mapping:
            overlay = create_speaker_map_overlay(session_id=session_id, mapping=mapping, author=author)
            overlay_id = str(overlay.get("overlay_id") or "").strip() or None

        session_state = set_speaker_overlay_for_transcript(session_id, transcript_version_id, overlay_id)
        refresh = refresh_speaker_maps_for_transcript(
            session_id=session_id,
            transcript_version_id=transcript_version_id,
        )
        view = _speaker_map_view_for_transcript(session_id, transcript_version_id)
        return {
            "session_id": session_id,
            "transcript_version_id": transcript_version_id,
            "speaker_overlay_id": view["speaker_overlay_id"],
            "speaker_map": view["speaker_map"],
            "overlay": overlay,
            "session_state": session_state,
            "index_refresh": refresh,
        }

    @app.get("/api/sessions/{session_id}/transcripts")
    async def api_session_transcripts(session_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        # QUEST_126: lazily backfill transcript versions for legacy sessions on access.
        ensure_legacy_transcript_versions(session_id)
        rows = list_transcript_versions(session_id)
        st = load_session_state(session_id)
        active_id = st.get("active_transcript_version_id")
        active_id = active_id.strip() if isinstance(active_id, str) and active_id.strip() else None

        out: list[Dict[str, Any]] = []
        for row in rows:
            trv_id = str(row.get("transcript_version_id") or "")
            if not trv_id:
                continue
            out.append(
                {
                    "id": trv_id,
                    "transcript_version_id": trv_id,
                    "run_id": str(row.get("run_id") or ""),
                    "session_id": str(row.get("session_id") or session_id),
                    "created_ts": row.get("created_ts"),
                    "diarization_enabled": bool(row.get("diarization_enabled")),
                    "asr_engine": str(row.get("asr_engine") or "default"),
                    "segments_count": int(row.get("segments_count") or 0),
                    "active": bool(active_id is not None and trv_id == active_id),
                }
            )
        out.sort(key=lambda r: (float(r.get("created_ts") or 0.0), str(r.get("transcript_version_id") or "")), reverse=True)
        start = max(int(offset), 0)
        end = start + max(int(limit), 1)
        page_rows = out[start:end]

        return ok(
            {
                "session_id": session_id,
                "transcripts": page_rows,
                "page": {"limit": int(limit), "offset": int(offset), "returned": len(page_rows), "total": len(out)},
            }
        )

    @app.get("/api/transcripts/{transcript_version_id}")
    async def api_transcript_get(transcript_version_id: str) -> Dict[str, Any]:
        # Back-compat: support legacy tv__run_id links.
        legacy_run_id = run_id_from_transcript_version_id(transcript_version_id)
        if legacy_run_id is not None:
            lay = init_stuart_root()
            run_json = lay.runs / legacy_run_id / "run.json"
            if not run_json.exists():
                return fail("NOT_FOUND", "transcript version not found", status=404)
            state = load_manifest(run_json)
            session_id = str(state.get("session_id") or "")
            if not session_id:
                return fail("NOT_FOUND", "transcript version not found", status=404)
            ensure_legacy_transcript_versions(session_id)
            versions = list_transcript_versions(session_id)
            matched = next((v for v in versions if str(v.get("run_id") or "") == legacy_run_id), None)
            if matched is None:
                return fail("NOT_FOUND", "transcript version not found", status=404)
            transcript_version_id = str(matched.get("transcript_version_id") or transcript_version_id)

        resolved = resolve_transcript_version(transcript_version_id)
        if not resolved:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        session_id = str(resolved.get("session_id") or "")
        if not session_id:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        try:
            payload = load_transcript_version(session_id, transcript_version_id)
        except FileNotFoundError:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        except Exception:
            return fail("INTERNAL_ERROR", "failed to load transcript version", status=500)

        segs = payload.get("segments")
        if not isinstance(segs, list):
            return fail("INTERNAL_ERROR", "invalid transcript schema", status=500)
        run_id = str(payload.get("run_id") or "")
        segments = [normalize_segment(seg, idx=i, run_id=run_id) for i, seg in enumerate(segs) if isinstance(seg, dict)]
        speaker_view = _speaker_map_view_for_transcript(session_id, transcript_version_id)
        speakers_set = set()
        for seg in segments:
            label = seg.get("speaker")
            if isinstance(label, str) and label.strip():
                speakers_set.add(label.strip().upper())
        return ok(
            {
                "transcript": {
                    "transcript_version_id": str(payload.get("transcript_version_id") or transcript_version_id),
                    "run_id": run_id,
                    "session_id": session_id,
                    "created_ts": payload.get("created_ts"),
                    "diarization_enabled": bool(payload.get("diarization_enabled")),
                    "asr_engine": str(payload.get("asr_engine") or "default"),
                    "audio_ref": payload.get("audio_ref") if isinstance(payload.get("audio_ref"), dict) else {},
                    "segments": segments,
                    "speaker_overlay_id": speaker_view["speaker_overlay_id"],
                    "speaker_map": speaker_view["speaker_map"],
                    "speakers": sorted(speakers_set),
                }
            }
        )

    @app.delete("/api/transcripts/{transcript_version_id}")
    async def api_delete_transcript(transcript_version_id: str, cascade: bool = False) -> Dict[str, Any]:
        resolved = resolve_transcript_version(transcript_version_id)
        if not resolved:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        session_id = str(resolved.get("session_id") or "")
        if not session_id:
            return fail("NOT_FOUND", "transcript version not found", status=404)

        deps = list_run_dependencies_for_transcript(session_id, transcript_version_id)
        consumers = deps.get("consumers") if isinstance(deps.get("consumers"), list) else []
        producers = deps.get("producers") if isinstance(deps.get("producers"), list) else []
        dependent_run_ids = sorted(
            {
                str(row.get("run_id") or "").strip()
                for row in (consumers + producers)
                if isinstance(row, dict) and str(row.get("run_id") or "").strip()
            }
        )
        if dependent_run_ids and not cascade:
            return JSONResponse(
                status_code=409,
                content={
                    "ok": False,
                    "error": "TRANSCRIPT_HAS_DEPENDENTS",
                    "session_id": session_id,
                    "transcript_version_id": transcript_version_id,
                    "dependents": {"consumers": consumers, "producers": producers},
                },
            )

        deleted_runs: list[str] = []
        for run_id in dependent_run_ids:
            try:
                delete_run_op(run_id)
                deleted_runs.append(run_id)
            except FileNotFoundError:
                continue

        try:
            delete_transcript_version(session_id, transcript_version_id)
        except FileNotFoundError:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        except Exception as e:
            return fail("INTERNAL_ERROR", f"failed to delete transcript version: {type(e).__name__}: {e}", status=500)

        lay = init_stuart_root()
        conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=lay.root))
        try:
            sqlite_fts.ensure_schema(conn)
            sqlite_fts.delete_transcript_version_rows(conn, transcript_version_id, run_ids=deleted_runs)
        finally:
            conn.close()

        return ok(
            {
                "session_id": session_id,
                "deleted_transcript_version_id": transcript_version_id,
                "deleted_runs": deleted_runs,
            }
        )

    @app.get("/api/transcripts/{transcript_version_id}/speaker_map")
    async def api_get_transcript_speaker_map(transcript_version_id: str) -> Dict[str, Any]:
        resolved = resolve_transcript_version(transcript_version_id)
        if not resolved:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        session_id = str(resolved.get("session_id") or "")
        if not session_id:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        try:
            load_transcript_version(session_id, transcript_version_id)
        except FileNotFoundError:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        except Exception:
            return fail("INTERNAL_ERROR", "failed to load transcript version", status=500)

        view = _speaker_map_view_for_transcript(session_id, transcript_version_id)
        return ok(
            {
                "session_id": session_id,
                "transcript_version_id": transcript_version_id,
                "speaker_overlay_id": view["speaker_overlay_id"],
                "speaker_map": view["speaker_map"],
            }
        )

    @app.put("/api/transcripts/{transcript_version_id}/speaker_map")
    async def api_put_transcript_speaker_map(transcript_version_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resolved = resolve_transcript_version(transcript_version_id)
        if not resolved:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        session_id = str(resolved.get("session_id") or "")
        if not session_id:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        try:
            load_transcript_version(session_id, transcript_version_id)
        except FileNotFoundError:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        except Exception:
            return fail("INTERNAL_ERROR", "failed to load transcript version", status=500)

        author_raw = payload.get("author")
        author = author_raw.strip() if isinstance(author_raw, str) and author_raw.strip() else "user"
        result = _save_speaker_map_for_transcript(
            session_id=session_id,
            transcript_version_id=transcript_version_id,
            mapping_raw=payload.get("mapping"),
            author=author,
        )
        return ok(result)

    @app.post("/api/transcripts/{transcript_version_id}/speaker_map")
    async def api_post_transcript_speaker_map(transcript_version_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await api_put_transcript_speaker_map(transcript_version_id, payload)

    @app.patch("/api/sessions/{session_id}/transcripts/active")
    async def api_set_active_transcript(session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        transcript_version_id = payload.get("transcript_version_id")
        if not isinstance(transcript_version_id, str) or not transcript_version_id.strip():
            return fail("INVALID_REQUEST", "transcript_version_id is required", status=400)
        transcript_version_id = transcript_version_id.strip()

        resolved = resolve_transcript_version(transcript_version_id)
        if not resolved:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        if str(resolved.get("session_id") or "") != session_id:
            return fail("INVALID_REQUEST", "transcript_version_id does not belong to session", status=400)

        try:
            load_transcript_version(session_id, transcript_version_id)
        except FileNotFoundError:
            return fail("NOT_FOUND", "transcript version not found", status=404)
        except Exception:
            return fail("INTERNAL_ERROR", "failed to load transcript version", status=500)

        st = set_active_transcript_version(session_id, transcript_version_id)
        return ok({"session_id": session_id, "session_state": st})

    @app.get("/api/sessions/{session_id}/formalizations")
    async def api_session_formalizations(session_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        rows = _runs_for_session(session_id, limit=max(int(limit), 1) * 4)
        out: list[Dict[str, Any]] = []
        lay = init_stuart_root()
        session_title = None
        sm_path = lay.sessions / session_id / "session.json"
        if sm_path.exists():
            try:
                sm = load_manifest(sm_path)
                raw_t = sm.get("title")
                if isinstance(raw_t, str):
                    session_title = raw_t
            except Exception:
                session_title = None

        for row in rows:
            downloads = (row.get("downloads") or {}).get("primary") or {}
            has_primary = any(downloads.get(k) for k in ("md", "txt", "json", "pdf", "evidence_map"))
            if not has_primary:
                continue

            plan = row.get("plan") if isinstance(row.get("plan"), dict) else {}
            steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
            formalize_params: Dict[str, Any] = {}
            for st in steps:
                if not isinstance(st, dict):
                    continue
                kind = (st.get("kind") or "").strip().lower()
                if kind == "formalize":
                    formalize_params = st.get("params") if isinstance(st.get("params"), dict) else {}
                    break

            mode = str(formalize_params.get("mode") or "meeting")
            template_id = str(formalize_params.get("template_id") or "default")
            retention = str(formalize_params.get("retention") or "MED")
            run_id = str(row.get("run_id"))
            title_override = normalize_formalization_title(row.get("title_override"))
            title = title_override or default_formalization_title(
                session_title=session_title,
                session_id=session_id,
                mode=mode,
                run_id=run_id,
            )
            consumed_tv = None
            if isinstance(row.get("primary_outputs"), dict):
                consumed_tv = row["primary_outputs"].get("consumed_transcript_version_id")
            if not consumed_tv:
                consumed_tv = formalize_params.get("transcript_version_id")

            primary_outputs = row.get("primary_outputs") if isinstance(row.get("primary_outputs"), dict) else {}
            md_src = (
                _artifact_path_for_primary(run_id, primary_outputs, "md")
                or _first_existing_artifact(run_id, ["minutes.md", "journal.md"])
            )
            json_src = (
                _artifact_path_for_primary(run_id, primary_outputs, "json")
                or _first_existing_artifact(run_id, ["minutes.json", "journal.json"])
            )
            evidence_src = (
                _artifact_path_for_primary(run_id, primary_outputs, "evidence_map")
                or _first_existing_artifact(run_id, ["evidence_map.json"])
            )

            output_markdown = _read_text(md_src) if md_src else None
            output_json = read_json(json_src) if json_src else None
            evidence_map = read_json(evidence_src) if evidence_src else None

            out.append(
                {
                    "id": run_id,
                    "formalization_id": run_id,
                    "run_id": run_id,
                    "session_id": session_id,
                    "title": title,
                    "status": row.get("status"),
                    "mode": mode,
                    "template_id": template_id,
                    "template": template_id,
                    "retention": retention,
                    "retention_level": retention,
                    "created_ts": row.get("created_ts"),
                    "downloads": row.get("downloads"),
                    "transcript_version_id": consumed_tv,
                    "output_markdown": output_markdown or "",
                    "output_json": output_json
                    if output_json is not None
                    else {
                        "run_id": run_id,
                        "status": row.get("status"),
                        "stage": row.get("stage"),
                        "progress": row.get("progress"),
                        "downloads": row.get("downloads"),
                        "artifacts": row.get("artifacts"),
                    },
                    "evidence_map": evidence_map if evidence_map is not None else [],
                    "pdf_url": downloads.get("pdf", {}).get("url") if isinstance(downloads.get("pdf"), dict) else None,
                }
            )
        out.sort(key=lambda r: (float(r.get("created_ts") or 0.0), str(r.get("run_id") or "")), reverse=True)
        start = max(int(offset), 0)
        end = start + max(int(limit), 1)
        page_rows = out[start:end]
        return ok(
            {
                "session_id": session_id,
                "formalizations": page_rows,
                "page": {"limit": int(limit), "offset": int(offset), "returned": len(page_rows), "total": len(out)},
            }
        )

    @app.get("/api/library")
    async def api_library(limit: int = 50, mode: Optional[str] = None) -> Dict[str, Any]:
        """Return sessions suitable for a library view.

        Source of truth:
        - Uses SQLite index (QUEST_059) so doors can list sessions + latest runs
          without scanning the filesystem.

        Notes:
        - If the index is empty, returns an empty list.
        - Does not create sessions or runs.
        """

        db_path = sqlite_fts.get_db_path()
        conn = sqlite_fts.connect(db_path)
        try:
            sqlite_fts.ensure_schema(conn)
            sessions = sqlite_fts.list_sessions(conn, limit=int(limit), mode=(mode or None))
            return {"ok": True, "sessions": [asdict(s) for s in sessions]}
        finally:
            conn.close()

    @app.post("/api/sessions")
    async def api_create_session(payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = (payload.get("mode") or "").strip().lower()
        title = payload.get("title") or None
        if not mode:
            return fail("INVALID_REQUEST", "mode is required", status=400)
        sid = create_session(mode=mode, title=title)
        return ok({"session_id": sid})

    @app.get("/api/sessions/{session_id}")
    async def api_session_detail(session_id: str) -> Dict[str, Any]:
        lay = init_stuart_root()
        mpath = lay.sessions / session_id / "session.json"
        if not mpath.exists():
            return fail("NOT_FOUND", "session not found", status=404)

        sm = load_manifest(mpath)
        state = load_session_state(session_id)
        title_override = state.get("title_override") if isinstance(state, dict) else None
        title_source = "state_override" if isinstance(title_override, str) and title_override.strip() else "session_manifest"
        effective_title = title_override if title_source == "state_override" else sm.get("title")

        runs = _runs_for_session(session_id, limit=200)
        run_rows = [
            {
                "run_id": r.get("run_id"),
                "status": r.get("status"),
                "stage": r.get("stage"),
                "progress": r.get("progress"),
                "created_ts": r.get("created_ts"),
            }
            for r in runs
        ]

        contributions: list[Dict[str, Any]] = []
        if lay.contributions.exists():
            for con_dir in lay.contributions.iterdir():
                if not con_dir.is_dir():
                    continue
                cpath = con_dir / "contribution.json"
                if not cpath.exists():
                    continue
                try:
                    cm = load_manifest(cpath)
                except Exception:
                    continue
                if str(cm.get("session_id") or "") != session_id:
                    continue
                contributions.append(
                    {
                        "contribution_id": cm.get("contribution_id") or con_dir.name,
                        "created_ts": cm.get("created_ts"),
                        "mime_type": cm.get("mime_type"),
                        "filename": cm.get("filename"),
                        "size_bytes": cm.get("size_bytes"),
                    }
                )
        contributions.sort(key=lambda c: (float(c.get("created_ts") or 0.0), str(c.get("contribution_id") or "")), reverse=True)

        transcripts_count = 0
        formalizations_count = 0
        for r in runs:
            arts = r.get("artifacts") or []
            if any((a.get("name") in {"transcript.json", "aligned_transcript.json"}) for a in arts):
                transcripts_count += 1
            primary = ((r.get("downloads") or {}).get("primary") or {})
            if primary.get("md") or primary.get("json") or primary.get("pdf"):
                formalizations_count += 1

        return ok(
            {
                "session": {
                    "session_id": session_id,
                    "created_ts": sm.get("created_ts"),
                    "mode": sm.get("mode"),
                    "title": effective_title,
                    "title_source": title_source,
                    "state": state,
                    "contributions": contributions,
                    "runs": run_rows,
                    "counts": {
                        "contributions": len(contributions),
                        "runs": len(runs),
                        "transcripts": transcripts_count,
                        "formalizations": formalizations_count,
                    },
                }
            }
        )

    @app.patch("/api/sessions/{session_id}")
    async def api_session_patch(session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        lay = init_stuart_root()
        mpath = lay.sessions / session_id / "session.json"
        if not mpath.exists():
            return fail("NOT_FOUND", "session not found", status=404)

        title_raw = payload.get("title")
        if not isinstance(title_raw, str):
            return fail("INVALID_REQUEST", "title must be a string", status=400)
        title = title_raw.strip()
        if not title:
            return fail("INVALID_REQUEST", "title cannot be empty", status=400)

        state = load_session_state(session_id)
        state["title_override"] = title
        state["updated_ts"] = time.time()
        state_path = lay.sessions / session_id / "session_state.json"
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        return ok({"session_id": session_id, "title": title, "title_source": "state_override"})

    @app.delete("/api/sessions/{session_id}")
    async def api_delete_session(session_id: str) -> Dict[str, Any]:
        try:
            result = delete_session_op(session_id)
        except FileNotFoundError:
            return fail("NOT_FOUND", "session not found", status=404)
        except Exception as e:
            return fail("INTERNAL_ERROR", f"failed to delete session: {type(e).__name__}: {e}", status=500)
        return ok(result)

    @app.post("/api/upload")
    async def api_upload(
        request: Request,
        session_id: Optional[str] = None,
        mode: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload media -> store as contribution (UPLOAD ≠ PROCESS).

        QUEST_062 policy rail:
          - Upload stores a contribution and (if needed) creates a session.
          - Upload does NOT start a run / transcribe / diarize / formalize.
          - Upload returns a deterministic plan preview using defaults:
              template=default, retention=MED, speakers=mode-default.

        We support two upload paths:
          1) Raw bytes body (no extra deps): send bytes in body + set headers:
             - Content-Type: audio/wav (or video/mp4, etc)
             - X-Filename: test.wav

          2) Multipart form-data (requires python-multipart): field name `file`.

        This keeps tests green in minimal environments while still supporting
        the browser upload UX where available.
        """

        # If caller didn't provide a session_id, create a fresh one (append-only).
        if not session_id:
            eff_mode = (mode or "meeting").strip().lower()
            mv = validate_mode(eff_mode)
            if not mv.ok or mv.canonical is None:
                return fail("INVALID_REQUEST", mv.message or "invalid mode", status=400)
            session_id = create_session(mode=mv.canonical, title=title or None)

        ct = (request.headers.get("content-type") or "").lower()

        con_id: Optional[str] = None
        meta: Optional[AttachmentMeta] = None

        # Multipart path (best UX), but may be unavailable in minimal envs.
        if ct.startswith("multipart/form-data"):
            try:
                form = await request.form()
            except RuntimeError as e:
                return fail(
                    "INVALID_REQUEST",
                    "multipart uploads not supported in this environment",
                    status=400,
                    details={"details": str(e), "hint": "Send raw bytes body + X-Filename header instead."},
                )

            file = form.get("file")
            if file is None:
                return fail("INVALID_REQUEST", "missing form field: file", status=400)

            try:
                con_id, meta = await store_upload(session_id=session_id, file=file)
            except Exception as e:
                return fail("INVALID_REQUEST", f"upload failed: {type(e).__name__}: {e}", status=400)

        else:
            # Raw bytes path (no python-multipart dependency)
            filename = request.headers.get("x-filename") or "upload.bin"
            data = await request.body()
            if not data:
                return fail("INVALID_REQUEST", "empty body", status=400)

            try:
                con_id, meta = await store_upload_bytes(
                    session_id=session_id,
                    filename=filename,
                    data=data,
                    mime_type=ct or None,
                )
            except Exception as e:
                return fail("INVALID_REQUEST", f"upload failed: {type(e).__name__}: {e}", status=400)

        if con_id is None or meta is None:
            return fail("INTERNAL_ERROR", "internal error: upload missing contribution/meta", status=500)

        # Determine effective mode for preview (prefer session manifest truth).
        sess_mode = (mode or "meeting").strip().lower() or "meeting"
        try:
            lay = init_stuart_root()
            sm = load_manifest(lay.sessions / session_id / "session.json")
            smode = sm.get("mode")
            if isinstance(smode, str) and smode.strip():
                sess_mode = smode.strip().lower()
        except Exception:
            pass

        # Plan preview (no run created).
        rr = RunRequest(mode=sess_mode)
        session_ctx = SessionContext(active_session_id=session_id, last_run_id=None)
        preview_out = clarify_or_preview(
            text="formalize",
            attachments=[meta],
            run_request=rr,
            session=session_ctx,
            door="web",
        )

        return ok({
            "session_id": session_id,
            "contribution_id": con_id,
            "attachment": asdict(meta),
            "plan_preview": asdict(preview_out.preview) if preview_out.preview else None,
            "needs_clarification": bool(preview_out.needs_clarification),
            "clarify": asdict(preview_out.clarify) if preview_out.clarify else None,
        })

    def _coerce_chat_request(payload: Dict[str, Any]) -> Dict[str, Any]:
        raw = dict(payload or {})
        if "text" not in raw and isinstance(raw.get("message"), str):
            raw["text"] = raw.get("message")
        if "ui" not in raw and isinstance(raw.get("ui_state"), dict):
            raw["ui"] = raw.get("ui_state")
        return raw

    def _transcript_version_for_run(session_id: str, run_id: str) -> Optional[str]:
        try:
            rows = list_transcript_versions(session_id)
        except Exception:
            return None
        for row in rows:
            if str(row.get("run_id") or "").strip() == run_id:
                out = str(row.get("transcript_version_id") or "").strip()
                if out:
                    return out
        return None

    def _augment_actions_from_hits(reply: ChatReplyV1, *, focus_session_id: Optional[str]) -> ChatReplyV1:
        actions = list(reply.actions or [])
        seen_open = {a.session_id for a in actions if isinstance(a, ChatActionOpenSessionV1)}
        seen_jump = {
            (a.session_id, int(a.segment_id))
            for a in actions
            if isinstance(a, ChatActionJumpToSegmentV1)
        }
        for h in reply.hits[:6]:
            sid = str(h.session_id)
            if focus_session_id is None or sid != focus_session_id:
                if sid not in seen_open:
                    actions.append(ChatActionOpenSessionV1(kind="open_session", session_id=sid))
                    seen_open.add(sid)
            key = (sid, int(h.citation.segment_id))
            if key not in seen_jump:
                trv = _transcript_version_for_run(sid, str(h.run_id))
                if trv:
                    actions.append(
                        ChatActionJumpToSegmentV1(
                            kind="jump_to_segment",
                            session_id=sid,
                            transcript_version_id=trv,
                            segment_id=int(h.citation.segment_id),
                        )
                    )
                    seen_jump.add(key)
        return ChatReplyV1(
            kind=reply.kind,
            text=reply.text,
            citations=list(reply.citations),
            hits=list(reply.hits),
            actions=actions,
            clarify=reply.clarify,
            planner=reply.planner,
        )

    @app.post("/api/chat")
    async def api_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            req = parse_chat_request_v1(_coerce_chat_request(payload))
        except Exception as e:
            return fail("INVALID_REQUEST", f"invalid chat payload: {type(e).__name__}: {e}", status=400)

        if not req.session_id:
            return fail("INVALID_REQUEST", "session_id is required for /api/chat; use /api/chat/global for cross-session queries", status=400)

        text = req.text.strip()
        cmd = parse_command(text)
        if cmd is not None:
            reply = handle_command(cmd, ui_state=req.ui)
            return ok({"session_id": req.session_id, "scope": "session", "reply": reply.to_dict()})

        hits = retrieve_hits(text, session_id=req.session_id, limit=10)
        evidence = hydrate_evidence(hits)
        if not evidence:
            reply = ChatReplyV1(
                kind="assistant",
                text="I couldn't find evidence for that in this session. Try Global scope to search across sessions.",
                citations=[],
                hits=[],
                actions=[],
            )
            return ok({"session_id": req.session_id, "scope": "session", "reply": reply.to_dict()})

        reply = answer_with_evidence(
            question=text,
            scope="session",
            ui_state=req.ui,
            history_tail=req.history_tail,
            evidence_segments=evidence,
            hits=hits,
        )
        reply = _augment_actions_from_hits(reply, focus_session_id=req.session_id)
        return ok({"session_id": req.session_id, "scope": "session", "reply": reply.to_dict()})

    @app.post("/api/chat/global")
    async def api_chat_global(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            req = parse_chat_request_v1(_coerce_chat_request(payload))
        except Exception as e:
            return fail("INVALID_REQUEST", f"invalid chat payload: {type(e).__name__}: {e}", status=400)

        text = req.text.strip()
        cmd = parse_command(text)
        if cmd is not None:
            reply = handle_command(cmd, ui_state=req.ui)
            return ok({"session_id": req.session_id, "scope": "global", "reply": reply.to_dict()})

        ui = dict(req.ui or {})
        focus_session_id = str(ui.get("selected_session_id") or req.session_id or "").strip() or None
        hits = retrieve_hits(text, session_id=focus_session_id, limit=10) if focus_session_id else []
        lower = text.lower()
        wants_cross = any(k in lower for k in ("all sessions", "which meeting", "how many meetings", "across sessions", "global"))
        if not hits or wants_cross:
            hits = retrieve_hits(text, session_id=None, limit=15)
        evidence = hydrate_evidence(hits)
        reply = answer_with_evidence(
            question=text,
            scope="global",
            ui_state=ui,
            history_tail=req.history_tail,
            evidence_segments=evidence,
            hits=hits,
        )
        reply = _augment_actions_from_hits(reply, focus_session_id=focus_session_id)
        return ok({"session_id": req.session_id, "scope": "global", "reply": reply.to_dict()})

    @app.post("/api/message")
    async def api_message(payload: Dict[str, Any]) -> Dict[str, Any]:
        text = (payload.get("text") or "")
        session_id = payload.get("session_id")
        ui_raw = payload.get("ui") or {}
        attachments_raw = payload.get("attachments") or []

        rr = RunRequest.from_dict(ui_raw) if isinstance(ui_raw, dict) else RunRequest()

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
            run_request=rr,
            session=session,
            door="web",
        )
        return ok({"result": asdict(out)})

    @app.post("/api/run")
    async def api_run(payload: Dict[str, Any], background: BackgroundTasks) -> Dict[str, Any]:
        """Create a run and execute it asynchronously (UI polls status)."""
        session_id = payload.get("session_id")
        ui_raw = payload.get("ui") or {}
        if not isinstance(session_id, str) or not session_id:
            return fail("INVALID_REQUEST", "session_id is required", status=400)
        if _session_contribution_count(session_id) <= 0:
            return fail("NO_AUDIO", "No audio uploaded for this session", status=400)

        rr_payload = dict(ui_raw) if isinstance(ui_raw, dict) else {}
        # Back-compat: allow transcript_version_id at top-level payload.
        if "transcript_version_id" not in rr_payload and isinstance(payload.get("transcript_version_id"), str):
            rr_payload["transcript_version_id"] = payload.get("transcript_version_id")
        rr = RunRequest.from_dict(rr_payload)
        if not rr.mode:
            return fail("INVALID_REQUEST", "mode is required to run", status=400)

        session = SessionContext(active_session_id=session_id, last_run_id=None)
        out = build_intent_and_plan(text="run", run_request=rr, session=session)

        # If the router flagged invalid selections, fail early with details.
        if not out.plan.validation.ok:
            return fail(
                "INVALID_REQUEST",
                "invalid run request",
                status=400,
                details={"issues": [asdict(i) for i in out.plan.validation.issues]},
            )

        plan = {"steps": [{"kind": s.kind.value, "params": dict(s.params)} for s in out.plan.steps]}
        title_override = normalize_formalization_title(ui_raw.get("formalization_title") if isinstance(ui_raw, dict) else None)
        run_id = create_run(session_id=session_id, plan=plan, title_override=title_override)

        # Run in background so the UI can poll progress.
        _spawn_run_job(run_id)

        state = get_run_state(run_id)
        return ok({"run_id": run_id, "state": state})

    @app.post("/api/transcribe")
    async def api_transcribe(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a transcribe-only run and execute asynchronously."""
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return fail("INVALID_REQUEST", "session_id is required", status=400)
        if _session_contribution_count(session_id) <= 0:
            return fail("NO_AUDIO", "No audio uploaded for this session", status=400)

        ui_raw = payload.get("ui") if isinstance(payload.get("ui"), dict) else payload
        mode = str(ui_raw.get("mode") or "meeting").strip().lower()
        if mode not in {"meeting", "journal"}:
            return fail("INVALID_REQUEST", "mode must be meeting or journal", status=400)
        diarization_enabled = ui_raw.get("diarization_enabled", ui_raw.get("diarize", True))
        if not isinstance(diarization_enabled, bool):
            diarization_enabled = True

        plan = {
            "steps": [
                {"kind": "validate", "params": {}},
                {
                    "kind": "transcribe",
                    "params": {
                        "mode": mode,
                        "session_id": session_id,
                        "diarization_enabled": diarization_enabled,
                    },
                },
            ]
        }
        run_id = create_run(session_id=session_id, plan=plan)
        _spawn_run_job(run_id)
        state = get_run_state(run_id)
        return ok({"run_id": run_id, "state": state})

    @app.delete("/api/runs/{run_id}")
    async def api_delete_run(run_id: str) -> Dict[str, Any]:
        try:
            result = delete_run_op(run_id)
        except FileNotFoundError:
            return fail("NOT_FOUND", "run not found", status=404)
        except Exception as e:
            return fail("INTERNAL_ERROR", f"failed to delete run: {type(e).__name__}: {e}", status=500)
        return ok(result)

    @app.patch("/api/runs/{run_id}")
    async def api_update_run(run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        title_raw = payload.get("formalization_title")
        if not isinstance(title_raw, str):
            return fail("INVALID_REQUEST", "formalization_title must be a string", status=400)
        title_norm = normalize_formalization_title(title_raw)
        if not title_norm:
            return fail("INVALID_REQUEST", "formalization_title cannot be empty", status=400)

        lay = init_stuart_root()
        run_path = lay.runs / run_id / "run.json"
        if not run_path.exists():
            return fail("NOT_FOUND", "run not found", status=404)

        try:
            state = load_manifest(run_path)
        except Exception as e:
            return fail("INTERNAL_ERROR", f"failed to load run manifest: {type(e).__name__}: {e}", status=500)

        state["title_override"] = title_norm
        try:
            save_manifest_atomic_overwrite(run_path, state)
        except Exception as e:
            return fail("INTERNAL_ERROR", f"failed to update run manifest: {type(e).__name__}: {e}", status=500)
        return ok({"run_id": run_id, "formalization_title": title_norm, "state": state})

    @app.get("/api/runs/{run_id}")
    async def api_run_status(run_id: str) -> Dict[str, Any]:
        state = get_run_state(run_id)
        return ok({
            "run_id": run_id,
            "state": state,
            # Explicit progress payload for UI polling (QUEST_063)
            "progress": poll_progress(run_id),
            # Deterministic downloads derived from run.json['primary_outputs'] (QUEST_063)
            "downloads": primary_downloads(run_id, state=state),
            # Full artifact listing (debug / secondary)
            "artifacts": list_run_artifacts(run_id),
        })

    @app.post("/api/runs/{run_id}/cancel")
    async def api_run_cancel(run_id: str) -> Dict[str, Any]:
        state = get_run_state(run_id)
        status = str(state.get("status") or "").strip().lower()
        if status in {"succeeded", "failed", "cancelled"}:
            return ok({"run_id": run_id, "status": status, "cancelled": False})

        lay = init_stuart_root()
        run_dir = lay.runs / run_id
        run_json = run_dir / "run.json"
        if not run_json.exists():
            return fail("NOT_FOUND", "run not found", status=404)

        cancel_path = run_dir / "inputs" / "cancel.json"
        cancel_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "run_id": run_id,
            "requested_ts": time.time(),
            "requested_by": "web_api",
        }
        if not cancel_path.exists():
            cancel_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return ok({"run_id": run_id, "cancelled": True, "cancel_receipt": str(cancel_path)})



    @app.get("/api/runs/{run_id}/speakers")
    async def api_run_speakers(run_id: str) -> Dict[str, Any]:
        """List distinct speaker labels observed for a run.

        Prefers aligned_transcript.json when available.
        """
        lay = init_stuart_root()
        run_dir = lay.runs / run_id
        artifacts_dir = run_dir / "artifacts"

        src = artifacts_dir / "aligned_transcript.json"
        if not src.exists():
            src = artifacts_dir / "transcript.json"

        if not src.exists():
            return JSONResponse(
                status_code=404,
                content={"ok": False, "run_id": run_id, "error": "transcript json missing"},
            )

        try:
            payload = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "run_id": run_id, "error": "failed to parse transcript json"},
            )

        segs = payload.get("segments") if isinstance(payload, dict) else []
        speakers_set = set()
        if isinstance(segs, list):
            for s in segs:
                if not isinstance(s, dict):
                    continue
                spk = s.get("speaker") or s.get("speaker_label")
                if isinstance(spk, str) and spk.strip():
                    speakers_set.add(spk.strip().upper())

        speakers = sorted(speakers_set)
        return {"ok": True, "run_id": run_id, "speakers": speakers, "source": src.name}


    @app.post("/api/runs/{run_id}/speaker_map")
    async def api_run_set_speaker_map(run_id: str, payload: Dict[str, Any], background: BackgroundTasks) -> Dict[str, Any]:
        """Back-compat endpoint that delegates to transcript-scoped speaker map persistence.

        Canonical path is /api/transcripts/{transcript_version_id}/speaker_map.
        """
        state = get_run_state(run_id)
        session_id = state.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return JSONResponse(status_code=404, content={"ok": False, "error": "run not found", "run_id": run_id})

        ensure_legacy_transcript_versions(session_id)
        transcript_version_id = None
        for row in list_transcript_versions(session_id):
            if str(row.get("run_id") or "") == run_id:
                transcript_version_id = str(row.get("transcript_version_id") or "").strip() or None
                if transcript_version_id:
                    break
        if not transcript_version_id:
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "error": "transcript version for run not found",
                    "run_id": run_id,
                    "session_id": session_id,
                },
            )

        author_raw = payload.get("author")
        author = author_raw.strip() if isinstance(author_raw, str) and author_raw.strip() else "web"
        result = _save_speaker_map_for_transcript(
            session_id=session_id,
            transcript_version_id=transcript_version_id,
            mapping_raw=payload.get("mapping"),
            author=author,
        )

        rerender_flag = payload.get("rerender")
        do_rerender = True if rerender_flag is None else bool(rerender_flag)

        rerender_run_id = None
        if do_rerender:
            lay = init_stuart_root()
            run_dir = lay.runs / run_id

            # Reuse the original run's formalize params when possible.
            formalize_params: Dict[str, Any] = {}
            plan0 = state.get("plan") if isinstance(state, dict) else {}
            steps0 = plan0.get("steps") if isinstance(plan0, dict) else []
            if isinstance(steps0, list):
                for st in steps0:
                    if not isinstance(st, dict):
                        continue
                    kind = st.get("kind")
                    if isinstance(kind, str) and kind.strip().lower() == "formalize":
                        p0 = st.get("params") if isinstance(st.get("params"), dict) else {}
                        formalize_params = dict(p0)
                        break

            if not formalize_params:
                formalize_params = {"mode": "meeting", "template_id": "default", "retention": "MED"}

            # Pin contribution_id from the prior run's resolved_input receipt (QUEST_031).
            try:
                rp = run_dir / "inputs" / "resolved_input.json"
                if rp.exists():
                    rp_json = json.loads(rp.read_text(encoding="utf-8"))
                    cid = rp_json.get("contribution_id")
                    if isinstance(cid, str) and cid.strip():
                        formalize_params["contribution_id"] = cid.strip()
            except Exception:
                pass

            # QUEST_071: This rerender is a formalize-only rerun.
            # Reuse transcript artifacts from the base run so we don't re-ingest audio.
            formalize_params["reuse_run_id"] = run_id

            # Ensure session_id is explicit for downstream tooling.
            formalize_params["session_id"] = session_id

            plan = {
                "steps": [
                    {"kind": "validate", "params": {}},
                    {"kind": "formalize", "params": formalize_params},
                ]
            }
            rerender_run_id = create_run(session_id=session_id, plan=plan)
            background.add_task(run_job, rerender_run_id)

        return {
            "ok": True,
            "run_id": run_id,
            "session_id": session_id,
            "transcript_version_id": transcript_version_id,
            "speaker_overlay_id": result.get("speaker_overlay_id"),
            "speaker_map": result.get("speaker_map"),
            "overlay": result.get("overlay"),
            "session_state": result.get("session_state"),
            "index_refresh": result.get("index_refresh"),
            "rerender_run_id": rerender_run_id,
        }

    @app.post("/api/runs/{run_id}/reformalize")
    async def api_run_reformalize(run_id: str, payload: Dict[str, Any], background: BackgroundTasks) -> Dict[str, Any]:
        """Create a formalize-only rerun for an existing run.

        Allows changing template/retention without re-uploading or retranscribing.

        Payload:
          {
            "template_id": "default",
            "retention": "MED"
          }
        """

        state = get_run_state(run_id)
        session_id = state.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return JSONResponse(status_code=404, content={"ok": False, "error": "run not found", "run_id": run_id})

        # Extract the base run's formalize params as defaults.
        base_params: Dict[str, Any] = {}
        plan0 = state.get("plan") if isinstance(state, dict) else {}
        steps0 = plan0.get("steps") if isinstance(plan0, dict) else []
        if isinstance(steps0, list):
            for st in steps0:
                if not isinstance(st, dict):
                    continue
                kind = st.get("kind")
                if isinstance(kind, str) and kind.strip().lower() == "formalize":
                    p0 = st.get("params") if isinstance(st.get("params"), dict) else {}
                    base_params = dict(p0)
                    break

        base_mode = (base_params.get("mode") or "meeting")
        base_template = (base_params.get("template_id") or base_params.get("template") or "default")
        base_retention = (base_params.get("retention") or "MED")

        # Apply overrides from payload.
        template_raw = payload.get("template_id")
        if template_raw is None:
            template_raw = payload.get("template")
        template_id = (str(template_raw).strip().lower() if template_raw is not None else str(base_template).strip().lower()) or "default"

        retention_raw = payload.get("retention")
        retention = (str(retention_raw).strip().upper() if retention_raw is not None else str(base_retention).strip().upper()) or "MED"

        # Pin contribution_id from the base run's resolved_input receipt (QUEST_031)
        # so reruns stay attached to the same uploaded media.
        contribution_id = None
        try:
            lay = init_stuart_root()
            rp = lay.runs / run_id / "inputs" / "resolved_input.json"
            if rp.exists():
                rp_json = json.loads(rp.read_text(encoding="utf-8"))
                cid = rp_json.get("contribution_id")
                if isinstance(cid, str) and cid.strip():
                    contribution_id = cid.strip()
        except Exception:
            contribution_id = None

        formalize_params: Dict[str, Any] = {
            "mode": str(base_mode).strip().lower() or "meeting",
            "template_id": template_id,
            "retention": retention,
            "session_id": session_id,
            # QUEST_070/071: reuse transcript substrate to avoid re-ingest.
            "reuse_run_id": run_id,
        }
        if contribution_id is not None:
            formalize_params["contribution_id"] = contribution_id

        plan = {
            "steps": [
                {"kind": "validate", "params": {}},
                {"kind": "formalize", "params": formalize_params},
            ]
        }

        try:
            rerun_run_id = create_run(session_id=session_id, plan=plan)
        except Exception as e:
            return JSONResponse(status_code=400, content={"ok": False, "error": f"failed to create rerun: {type(e).__name__}: {e}"})

        _spawn_run_job(rerun_run_id)
        return {
            "ok": True,
            "base_run_id": run_id,
            "rerun_run_id": rerun_run_id,
            "session_id": session_id,
            "params": dict(formalize_params),
        }
    @app.get("/api/runs/{run_id}/progress")
    async def api_run_progress(run_id: str) -> Dict[str, Any]:
        return poll_progress(run_id)

    @app.get("/api/sessions/{session_id}/export")
    async def api_session_export(
        session_id: str,
        export_type: str = "full_bundle",
        format: Optional[str] = None,
        transcript_formats: Optional[str] = None,
        formalization_formats: Optional[str] = None,
    ) -> Any:
        lay = init_stuart_root()
        session_manifest_path = lay.sessions / session_id / "session.json"
        if not session_manifest_path.exists():
            return fail("NOT_FOUND", "session not found", status=404)

        et = (export_type or "full_bundle").strip().lower()
        if et not in {"full_bundle", "transcript_only", "formalization_only", "dev_bundle"}:
            return fail("INVALID_REQUEST", "invalid export_type", status=400)

        def _parse_csv(raw: Optional[str], *, allowed: set[str], default: list[str], key: str) -> tuple[Optional[list[str]], Optional[str]]:
            if raw is None:
                return list(default), None
            parts = [str(x).strip().lower() for x in str(raw).split(",")]
            vals = [p for p in parts if p]
            if not vals:
                return list(default), None
            bad = sorted({v for v in vals if v not in allowed})
            if bad:
                return None, f"invalid {key}: {','.join(bad)}"
            dedup: list[str] = []
            seen: set[str] = set()
            for v in vals:
                if v in seen:
                    continue
                seen.add(v)
                dedup.append(v)
            return dedup, None

        transcript_vals: list[str] = []
        formalization_vals: list[str] = []
        if et == "dev_bundle":
            transcript_vals = []
            formalization_vals = []
        else:
            transcript_vals, err_t = _parse_csv(
                transcript_formats,
                allowed={"txt", "md", "pdf"},
                default=["txt"],
                key="transcript_formats",
            )
            if err_t:
                return fail("INVALID_REQUEST", err_t, status=400)
            formalization_vals, err_f = _parse_csv(
                formalization_formats,
                allowed={"md", "pdf"},
                default=["pdf"],
                key="formalization_formats",
            )
            if err_f:
                return fail("INVALID_REQUEST", err_f, status=400)

        try:
            res = export_session_bundle(
                session_id,
                export_type=et,
                transcript_formats=transcript_vals,
                formalization_formats=formalization_vals,
            )
            zip_path = Path(res.zip_path)
        except FileExistsError:
            candidates = sorted(lay.exports.glob(f"{session_id}__export_{et}__*.zip"))
            if not candidates:
                return fail("INTERNAL_ERROR", "export already exists but could not be resolved", status=500)
            zip_path = candidates[-1]
        except Exception as e:
            return fail("INTERNAL_ERROR", f"export failed: {type(e).__name__}: {e}", status=500)

        if not zip_path.exists():
            return fail("INTERNAL_ERROR", "export zip missing after creation", status=500)

        try:
            session_manifest = load_manifest(session_manifest_path)
        except Exception:
            session_manifest = {}
        title_raw = session_manifest.get("title") if isinstance(session_manifest, dict) else None
        title_clean = normalize_formalization_title(title_raw) if isinstance(title_raw, str) else None
        title_slug = ""
        if title_clean:
            title_slug = (
                "".join(ch.lower() if (ch.isalnum() or ch in {"_", "-"}) else "_" for ch in title_clean)
                .strip("_")
            )
        download_name = f"{session_id}__export_{et}.zip"
        if title_slug:
            download_name = f"{session_id}__{title_slug}__export_{et}.zip"

        # Backward-compat for existing frontend behavior expecting blob bytes.
        if (format or "").strip().lower() == "zip":
            return FileResponse(path=str(zip_path), filename=download_name)

        h = hashlib.sha256()
        with zip_path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)

        return ok(
            {
                "session_id": session_id,
                "export_type": et,
                "zip": {
                    "name": zip_path.name,
                    "path": str(zip_path),
                    "download_name": download_name,
                    "sha256": h.hexdigest(),
                    "size_bytes": zip_path.stat().st_size,
                    "download_url": f"/api/exports/{zip_path.name}",
                },
                "transcript_formats": transcript_vals,
                "formalization_formats": formalization_vals,
            }
        )

    @app.get("/api/exports/{filename}")
    async def api_export_download(filename: str) -> Any:
        if "/" in filename or "\\" in filename or ".." in filename:
            return fail("INVALID_REQUEST", "invalid filename", status=400)
        lay = init_stuart_root()
        p = lay.exports / filename
        if not p.exists() or not p.is_file():
            return fail("NOT_FOUND", "export file not found", status=404)
        return FileResponse(path=str(p), filename=filename)

    @app.get("/download/{run_id}/{filename}")
    async def download_artifact(run_id: str, filename: str) -> Any:
        return artifact_response(run_id, filename)

    @app.get("/api/search")
    async def api_search(q: str, session_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        db_path = sqlite_fts.get_db_path()
        conn = sqlite_fts.connect(db_path)
        try:
            hits = sqlite_fts.search(conn, q, limit=int(limit), session_id=session_id)
            return {"ok": True, "hits": [asdict(h) for h in hits]}
        finally:
            conn.close()

    @app.post("/api/ui/event")
    async def api_ui_event(request: Request) -> Dict[str, Any]:
        try:
            payload = await request.json()
        except Exception:
            return fail("INVALID_REQUEST", "invalid JSON body", status=400)
        if not isinstance(payload, dict):
            return fail("INVALID_REQUEST", "invalid payload", status=400)

        event_name = str(payload.get("event") or "").strip()
        if not event_name:
            return fail("INVALID_REQUEST", "event is required", status=400)

        session_val = payload.get("session_id")
        run_val = payload.get("run_id")
        session_id = str(session_val).strip() if session_val is not None else None
        run_id = str(run_val).strip() if run_val is not None else None
        summary = str(payload.get("summary") or event_name).strip() or event_name
        data_obj = payload.get("data")
        if not isinstance(data_obj, dict):
            data_obj = {}

        correlation_id = (request.headers.get("X-Correlation-Id") or "").strip() or str(uuid.uuid4())
        trace_id = correlation_id
        span_id = str(uuid.uuid4())

        level = "INFO"
        if event_name in {"ui.error", "ui.fetch_failed"}:
            level = "ERROR"

        obs_events.emit_event(
            level=level,
            source="frontend",
            component="ui",
            event=event_name,
            summary=summary,
            correlation_id=correlation_id,
            session_id=session_id,
            run_id=run_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=getattr(request.state, "span_id", None),
            data=data_obj,
        )

        if event_name == "ui.error":
            obs_events.emit_alert(
                level="ERROR",
                source="frontend",
                component="ui",
                event="alert.ui_error",
                summary=summary,
                correlation_id=correlation_id,
                session_id=session_id,
                run_id=run_id,
                trace_id=trace_id,
                span_id=str(uuid.uuid4()),
                parent_span_id=span_id,
                data=data_obj,
            )
        elif event_name == "ui.fetch_failed":
            obs_events.emit_alert(
                level="ERROR",
                source="frontend",
                component="ui",
                event="alert.ui_fetch_failed",
                summary=summary,
                correlation_id=correlation_id,
                session_id=session_id,
                run_id=run_id,
                trace_id=trace_id,
                span_id=str(uuid.uuid4()),
                parent_span_id=span_id,
                data=data_obj,
            )

        return ok({"accepted": True, "event": event_name})

    return app


app = create_app()
