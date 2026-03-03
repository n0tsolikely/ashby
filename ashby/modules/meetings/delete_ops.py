from __future__ import annotations

import shutil
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import load_manifest
from ashby.modules.meetings.index import sqlite_fts


def _run_session_id(run_dir: Path) -> Optional[str]:
    run_json = run_dir / "run.json"
    if not run_json.exists():
        return None
    payload = _load_manifest_relaxed(run_json)
    if not isinstance(payload, dict):
        return None
    sid = str(payload.get("session_id") or "").strip()
    return sid or None


def _load_manifest_relaxed(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = load_manifest(path)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _run_manifest(run_dir: Path) -> Optional[Dict[str, Any]]:
    run_json = run_dir / "run.json"
    if not run_json.exists():
        return None
    return _load_manifest_relaxed(run_json)


def list_runs_for_session(session_id: str) -> List[str]:
    lay = init_stuart_root()
    sid = str(session_id or "").strip()
    out: List[str] = []
    if not sid or not lay.runs.exists():
        return out
    for run_dir in sorted(lay.runs.iterdir()):
        if not run_dir.is_dir():
            continue
        if _run_session_id(run_dir) == sid:
            out.append(run_dir.name)
    return out


def list_run_dependencies_for_transcript(session_id: str, transcript_version_id: str) -> Dict[str, List[Dict[str, Any]]]:
    lay = init_stuart_root()
    sid = str(session_id or "").strip()
    trv = str(transcript_version_id or "").strip()
    consumers: List[Dict[str, Any]] = []
    producers: List[Dict[str, Any]] = []
    if not sid or not trv or not lay.runs.exists():
        return {"consumers": consumers, "producers": producers}

    for run_dir in sorted(lay.runs.iterdir()):
        if not run_dir.is_dir():
            continue
        st = _run_manifest(run_dir)
        if not isinstance(st, dict):
            continue
        if str(st.get("session_id") or "") != sid:
            continue
        run_id = str(st.get("run_id") or run_dir.name)
        po = st.get("primary_outputs") if isinstance(st.get("primary_outputs"), dict) else {}
        consumed = str(po.get("consumed_transcript_version_id") or "").strip()
        produced = str(po.get("produced_transcript_version_id") or "").strip()

        if not consumed:
            plan = st.get("plan") if isinstance(st.get("plan"), dict) else {}
            steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if str(step.get("kind") or "").strip().lower() != "formalize":
                    continue
                params = step.get("params") if isinstance(step.get("params"), dict) else {}
                consumed = str(params.get("transcript_version_id") or "").strip()
                break

        row = {"run_id": run_id, "status": st.get("status"), "created_ts": st.get("created_ts")}
        if consumed == trv:
            consumers.append(row)
        if produced == trv:
            producers.append(row)

    return {"consumers": consumers, "producers": producers}


def delete_run(run_id: str) -> Dict[str, Any]:
    lay = init_stuart_root()
    rid = str(run_id or "").strip()
    run_dir = lay.runs / rid
    if not rid or not run_dir.exists() or not run_dir.is_dir():
        raise FileNotFoundError(f"run not found: {run_id}")

    sid = _run_session_id(run_dir)
    shutil.rmtree(run_dir, ignore_errors=False)

    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=lay.root))
    try:
        sqlite_fts.ensure_schema(conn)
        sqlite_fts.delete_run_rows(conn, rid)
    finally:
        conn.close()

    return {
        "run_id": rid,
        "session_id": sid,
        "deleted": {"run": 1},
    }


def _resolve_session_identities(session_id: str) -> Tuple[List[Path], List[str]]:
    lay = init_stuart_root()
    sid = str(session_id or "").strip()
    matched_dirs: list[Path] = []
    identity_keys: set[str] = {sid}

    if lay.sessions.exists():
        for sdir in lay.sessions.iterdir():
            if not sdir.is_dir():
                continue
            manifest_id = ""
            mpath = sdir / "session.json"
            if mpath.exists():
                sm = _load_manifest_relaxed(mpath)
                manifest_id = str(sm.get("session_id") or "") if isinstance(sm, dict) else ""
            if sdir.name == sid or manifest_id == sid:
                matched_dirs.append(sdir)
                identity_keys.add(sdir.name)
                if manifest_id:
                    identity_keys.add(manifest_id)
    return matched_dirs, sorted(identity_keys)


def delete_session(session_id: str) -> Dict[str, Any]:
    lay = init_stuart_root()
    matched_dirs, identity_keys = _resolve_session_identities(session_id)
    if not matched_dirs:
        raise FileNotFoundError(f"session not found: {session_id}")

    deleted_runs: list[str] = []
    deleted = {"session": 0, "runs": 0, "contributions": 0, "overlays": 0}

    if lay.runs.exists():
        for run_dir in list(lay.runs.iterdir()):
            if not run_dir.is_dir():
                continue
            sid = _run_session_id(run_dir)
            if sid not in set(identity_keys):
                continue
            deleted_runs.append(run_dir.name)
            shutil.rmtree(run_dir, ignore_errors=False)
            deleted["runs"] += 1

    for sdir in matched_dirs:
        shutil.rmtree(sdir, ignore_errors=False)
        deleted["session"] += 1

    if lay.contributions.exists():
        for con_dir in list(lay.contributions.iterdir()):
            if not con_dir.is_dir():
                continue
            con_json = con_dir / "contribution.json"
            if not con_json.exists():
                continue
            c = _load_manifest_relaxed(con_json)
            if not isinstance(c, dict):
                continue
            if str(c.get("session_id") or "") not in set(identity_keys):
                continue
            shutil.rmtree(con_dir, ignore_errors=False)
            deleted["contributions"] += 1

    for sid in identity_keys:
        overlay_dir = lay.overlays / sid
        if overlay_dir.exists():
            shutil.rmtree(overlay_dir, ignore_errors=False)
            deleted["overlays"] += 1

    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=lay.root))
    try:
        sqlite_fts.ensure_schema(conn)
        for rid in deleted_runs:
            sqlite_fts.delete_run_rows(conn, rid)
        for sid in identity_keys:
            sqlite_fts.delete_session_rows(conn, sid)
    finally:
        conn.close()

    return {
        "session_id": session_id,
        "resolved_keys": identity_keys,
        "deleted_runs": deleted_runs,
        "deleted": deleted,
    }
