from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import load_manifest
from ashby.modules.meetings.overlays import load_speaker_map_overlay
from ashby.modules.meetings.render.export_pdf import _build_text_pdf_bytes
from ashby.modules.meetings.session_state import load_session_state
from ashby.modules.meetings.template_registry import load_template_spec
from ashby.modules.meetings.transcript_versions import list_transcript_versions, load_transcript_version


_DETERMINISTIC_ZIP_DT = (2000, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ExportBundleResult:
    session_id: str
    zip_path: str
    files_added: int
    run_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "session_id": self.session_id,
            "zip_path": self.zip_path,
            "files_added": int(self.files_added),
        }
        if self.run_id:
            d["run_id"] = self.run_id
        return d


def _safe_rel(root: Path, p: Path) -> Optional[str]:
    try:
        rel = p.resolve().relative_to(root.resolve())
    except Exception:
        return None
    return rel.as_posix()


def _iter_files_recursive(dir_path: Path) -> Iterable[Path]:
    for p in sorted(dir_path.rglob("*")):
        if p.is_file():
            yield p


def _json_bytes(payload: Dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sanitize_json_paths(obj: object, *, root: Path) -> object:
    if isinstance(obj, dict):
        return {str(k): _sanitize_json_paths(v, root=root) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json_paths(v, root=root) for v in obj]
    if isinstance(obj, str):
        s = obj.strip()
        # Only sanitize likely filesystem absolute paths, not URL paths.
        if s.startswith("/home/") or s.startswith("/tmp/") or re.match(r"^[A-Za-z]:\\\\", s):
            try:
                rel = _safe_rel(root, Path(s))
            except Exception:
                rel = None
            if rel:
                return rel
            try:
                return Path(s).name or s
            except Exception:
                return s
        return obj
    return obj


def _speaker_display(raw: str, mapping: Dict[str, str]) -> str:
    key = str(raw or "").strip().upper()
    if key in mapping and str(mapping[key]).strip():
        return str(mapping[key]).strip()
    m = re.match(r"^SPEAKER_(\d+)$", key)
    if m:
        idx = int(m.group(1)) + 1
        return f"Speaker-{idx:02d}"
    if key:
        return key
    return "Speaker-01"


def _format_transcript_lines(payload: Dict[str, object], mapping: Dict[str, str]) -> List[str]:
    segs = payload.get("segments")
    if not isinstance(segs, list):
        return ["(no transcript segments)"]

    out: List[str] = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        speaker = _speaker_display(str(seg.get("speaker") or ""), mapping)
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        out.append(f"{speaker}: {text}")
    return out or ["(no transcript segments)"]


def _build_transcript_txt(*, session_id: str, transcript_version_id: str, created_ts: Optional[float], lines: List[str]) -> bytes:
    created = "unknown"
    if isinstance(created_ts, (int, float)):
        created = str(float(created_ts))
    head = [
        f"session_id: {session_id}",
        f"transcript_version_id: {transcript_version_id}",
        f"created_ts: {created}",
        "",
    ]
    return ("\n".join(head + lines) + "\n").encode("utf-8")


def _build_transcript_md(*, session_id: str, transcript_version_id: str, created_ts: Optional[float], lines: List[str]) -> bytes:
    created = "unknown"
    if isinstance(created_ts, (int, float)):
        created = str(float(created_ts))
    comment = (
        f"<!-- session_id:{session_id}; transcript_version_id:{transcript_version_id}; "
        f"generated_at:{created} -->\n\n"
    )
    body = "\n".join(f"- {ln}" for ln in lines) + "\n"
    return (comment + body).encode("utf-8")


def _build_transcript_pdf(*, session_id: str, transcript_version_id: str, created_ts: Optional[float], lines: List[str]) -> bytes:
    created = "unknown"
    if isinstance(created_ts, (int, float)):
        created = str(float(created_ts))
    body = "\n".join(lines)
    footer = f"session:{session_id}  transcript:{transcript_version_id}  created:{created}"
    return _build_text_pdf_bytes(body, title="Transcript", footer_text=footer)


def _resolve_overlay_map(session_id: str, transcript_version_id: str) -> Tuple[Optional[str], Dict[str, str]]:
    st = load_session_state(session_id)
    by_tr = st.get("speaker_overlays_by_transcript")
    overlay_id: Optional[str] = None
    if isinstance(by_tr, dict):
        raw = by_tr.get(transcript_version_id)
        if isinstance(raw, str) and raw.strip():
            overlay_id = raw.strip()
    if overlay_id is None:
        active_trv = st.get("active_transcript_version_id")
        if isinstance(active_trv, str) and active_trv.strip() == transcript_version_id:
            raw = st.get("active_speaker_overlay_id")
            if isinstance(raw, str) and raw.strip():
                overlay_id = raw.strip()

    if not overlay_id:
        return None, {}

    try:
        mapping = load_speaker_map_overlay(session_id, overlay_id)
    except Exception:
        return overlay_id, {}
    return overlay_id, dict(mapping)


def _session_runs(session_id: str) -> List[Tuple[float, str, Dict[str, object], Path]]:
    lay = init_stuart_root()
    rows: List[Tuple[float, str, Dict[str, object], Path]] = []
    if not lay.runs.exists():
        return rows
    for run_dir in sorted(lay.runs.iterdir()):
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
        rid = str(state.get("run_id") or run_dir.name)
        created = float(state.get("created_ts") or 0.0)
        rows.append((created, rid, state, run_dir))
    rows.sort(key=lambda t: (t[0], t[1]))
    return rows


def _normalize_format_list(values: Optional[List[str]], *, default: List[str], allowed: set[str]) -> List[str]:
    if not values:
        values = list(default)
    out: List[str] = []
    seen: set[str] = set()
    for raw in values:
        v = str(raw or "").strip().lower()
        if not v or v not in allowed or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _formalization_mode(run_state: Dict[str, object]) -> str:
    po = run_state.get("primary_outputs")
    if isinstance(po, dict):
        m = str(po.get("mode") or "").strip().lower()
        if m in {"meeting", "journal"}:
            return m

    plan = run_state.get("plan")
    if isinstance(plan, dict):
        steps = plan.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if str(step.get("kind") or "").strip().lower() != "formalize":
                    continue
                params = step.get("params") if isinstance(step.get("params"), dict) else {}
                m = str(params.get("mode") or "").strip().lower()
                if m in {"meeting", "journal"}:
                    return m
    return "meeting"


def _candidate_paths(run_dir: Path, rels: List[str]) -> Optional[Path]:
    for rel in rels:
        p = run_dir / rel
        if p.exists() and p.is_file():
            return p
    return None


def _find_primary_output_path(run_dir: Path, run_state: Dict[str, object], key: str) -> Optional[Path]:
    po = run_state.get("primary_outputs")
    if not isinstance(po, dict):
        return None
    ptr = po.get(key)
    if not isinstance(ptr, dict):
        return None
    rel = ptr.get("path")
    if not isinstance(rel, str) or not rel.strip():
        return None
    p = (run_dir / rel).resolve()
    try:
        p.relative_to(run_dir.resolve())
    except Exception:
        return None
    if p.exists() and p.is_file():
        return p
    return None


def _build_entries_for_session(
    session_id: str,
    *,
    export_type: str,
    transcript_formats: Optional[List[str]] = None,
    formalization_formats: Optional[List[str]] = None,
) -> Dict[str, bytes]:
    lay = init_stuart_root()
    session_json = lay.sessions / session_id / "session.json"
    if not session_json.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {session_json}")

    session_manifest = load_manifest(session_json)
    session_title = str(session_manifest.get("title") or "").strip() or session_id

    entries: Dict[str, bytes] = {}
    entries["session.json"] = _json_bytes({"session_id": session_id, "session_title": session_title})

    # audio/
    if lay.contributions.exists():
        for con_dir in sorted(lay.contributions.iterdir()):
            if not con_dir.is_dir():
                continue
            man = con_dir / "contribution.json"
            if not man.exists():
                continue
            try:
                c = load_manifest(man)
            except Exception:
                continue
            if str(c.get("session_id") or "") != session_id:
                continue
            cid = str(c.get("contribution_id") or con_dir.name)
            for p in sorted(con_dir.iterdir()):
                if not p.is_file() or p.name == "contribution.json":
                    continue
                arc = f"audio/{cid}__{p.name}"
                entries[arc] = p.read_bytes()

    et = (export_type or "full_bundle").strip().lower()
    include_transcripts = et in {"full_bundle", "transcript_only", "dev_bundle"}
    include_formalizations = et in {"full_bundle", "formalization_only", "dev_bundle"}
    include_dev = et == "dev_bundle"

    t_formats = _normalize_format_list(transcript_formats, default=["txt"], allowed={"txt", "md", "pdf"})
    f_formats = _normalize_format_list(formalization_formats, default=["pdf"], allowed={"md", "pdf"})
    if et == "dev_bundle":
        t_formats = ["txt", "md", "pdf"]
        f_formats = ["md", "pdf"]

    if include_transcripts:
        versions = list_transcript_versions(session_id)
        versions = sorted(
            versions,
            key=lambda row: (float(row.get("created_ts") or 0.0), str(row.get("transcript_version_id") or "")),
        )
        for row in versions:
            trv = str(row.get("transcript_version_id") or "").strip()
            if not trv:
                continue
            payload = load_transcript_version(session_id, trv)
            created_ts = payload.get("created_ts")
            created_val = float(created_ts) if isinstance(created_ts, (int, float)) else None

            overlay_id, mapping = _resolve_overlay_map(session_id, trv)
            if mapping:
                overlay_payload = {
                    "session_id": session_id,
                    "transcript_version_id": trv,
                    "overlay_id": overlay_id,
                    "mapping": mapping,
                }
                entries[f"overlays/transcripts/{trv}/speaker_map.json"] = _json_bytes(overlay_payload)

            lines = _format_transcript_lines(payload, mapping)
            if "txt" in t_formats:
                entries[f"transcripts/{trv}/transcript.txt"] = _build_transcript_txt(
                    session_id=session_id,
                    transcript_version_id=trv,
                    created_ts=created_val,
                    lines=lines,
                )
            if "md" in t_formats:
                entries[f"transcripts/{trv}/transcript.md"] = _build_transcript_md(
                    session_id=session_id,
                    transcript_version_id=trv,
                    created_ts=created_val,
                    lines=lines,
                )
            if "pdf" in t_formats:
                entries[f"transcripts/{trv}/transcript.pdf"] = _build_transcript_pdf(
                    session_id=session_id,
                    transcript_version_id=trv,
                    created_ts=created_val,
                    lines=lines,
                )

            if include_dev:
                entries[f"dev/transcripts/{trv}/transcript_version.json"] = _json_bytes(
                    _sanitize_json_paths(payload, root=lay.root)  # type: ignore[arg-type]
                )

    if include_formalizations or include_dev:
        for _created, rid, run_state, run_dir in _session_runs(session_id):
            mode = _formalization_mode(run_state)
            md_name = "minutes.md" if mode == "meeting" else "journal.md"
            pdf_name = "minutes.pdf" if mode == "meeting" else "journal.pdf"
            json_name = "minutes.json" if mode == "meeting" else "journal.json"

            md_path = _find_primary_output_path(run_dir, run_state, "md") or _candidate_paths(run_dir, [f"artifacts/{md_name}"])
            pdf_path = _find_primary_output_path(run_dir, run_state, "pdf") or _candidate_paths(run_dir, [f"exports/{pdf_name}", f"artifacts/{pdf_name}"])
            raw_json_path = _find_primary_output_path(run_dir, run_state, "json") or _candidate_paths(run_dir, [f"artifacts/{json_name}"])
            evidence_path = _find_primary_output_path(run_dir, run_state, "evidence_map") or _candidate_paths(
                run_dir,
                ["artifacts/evidence_map.json", "artifacts/evidence_map_llm.json"],
            )
            llm_usage_path = _candidate_paths(run_dir, ["artifacts/llm_usage.json"])
            run_json_path = run_dir / "run.json"
            events_path = run_dir / "events.jsonl"

            has_user_output = False
            if include_formalizations:
                if "md" in f_formats and md_path and md_path.exists():
                    entries[f"formalizations/{rid}/{md_name}"] = md_path.read_bytes()
                    has_user_output = True
                if "pdf" in f_formats and pdf_path and pdf_path.exists():
                    entries[f"formalizations/{rid}/{pdf_name}"] = pdf_path.read_bytes()
                    has_user_output = True

            if include_dev and (has_user_output or raw_json_path or evidence_path or llm_usage_path):
                if run_json_path.exists():
                    try:
                        run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
                        entries[f"dev/formalizations/{rid}/run.json"] = _json_bytes(
                            _sanitize_json_paths(run_payload, root=lay.root)  # type: ignore[arg-type]
                        )
                    except Exception:
                        entries[f"dev/formalizations/{rid}/run.json"] = run_json_path.read_bytes()
                if events_path.exists():
                    entries[f"dev/formalizations/{rid}/events.jsonl"] = events_path.read_bytes()
                if evidence_path and evidence_path.exists():
                    try:
                        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                        entries[f"dev/formalizations/{rid}/evidence_map.json"] = _json_bytes(
                            _sanitize_json_paths(evidence_payload, root=lay.root)  # type: ignore[arg-type]
                        )
                    except Exception:
                        entries[f"dev/formalizations/{rid}/evidence_map.json"] = evidence_path.read_bytes()
                if llm_usage_path and llm_usage_path.exists():
                    try:
                        llm_payload = json.loads(llm_usage_path.read_text(encoding="utf-8"))
                        entries[f"dev/formalizations/{rid}/llm_usage_receipt.json"] = _json_bytes(
                            _sanitize_json_paths(llm_payload, root=lay.root)  # type: ignore[arg-type]
                        )
                    except Exception:
                        entries[f"dev/formalizations/{rid}/llm_usage_receipt.json"] = llm_usage_path.read_bytes()
                if raw_json_path and raw_json_path.exists():
                    try:
                        out_payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
                        entries[f"dev/formalizations/{rid}/{json_name}"] = _json_bytes(
                            _sanitize_json_paths(out_payload, root=lay.root)  # type: ignore[arg-type]
                        )
                    except Exception:
                        entries[f"dev/formalizations/{rid}/{json_name}"] = raw_json_path.read_bytes()
                    try:
                        out_payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
                        tpl_id = str(out_payload.get("template_id") or "").strip()
                        tpl_mode = str(out_payload.get("mode") or mode or "").strip().lower()
                        tpl_ver = out_payload.get("template_version")
                        if tpl_id and tpl_mode in {"meeting", "journal"} and tpl_ver is not None:
                            tpl_spec = load_template_spec(tpl_mode, tpl_id, version=tpl_ver)
                            safe_source_path = _safe_rel(lay.root, tpl_spec.path) or tpl_spec.path.name
                            tpl_meta = {
                                "template_id": tpl_spec.template_id,
                                "template_title": tpl_spec.template_title,
                                "template_version": tpl_spec.template_version,
                                "mode": tpl_mode,
                                "source_path": safe_source_path,
                            }
                            base = f"dev/templates/{rid}/{tpl_spec.template_id}/v{tpl_spec.template_version}"
                            entries[f"{base}/metadata.json"] = _json_bytes(tpl_meta)
                            entries[f"{base}/template.md"] = tpl_spec.raw_text.encode("utf-8")
                    except Exception:
                        # Dev template capture is best-effort and must not block export.
                        pass

    return entries


def export_session_bundle(
    session_id: str,
    *,
    export_type: str = "full_bundle",
    transcript_formats: Optional[List[str]] = None,
    formalization_formats: Optional[List[str]] = None,
    out_dir: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> ExportBundleResult:
    lay = init_stuart_root()
    sess_json = lay.sessions / session_id / "session.json"
    if not sess_json.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {sess_json}")

    sess = load_manifest(sess_json)
    created_ts = sess.get("created_ts")
    if not isinstance(created_ts, (int, float)):
        created_ts = None

    et = (export_type or "full_bundle").strip().lower()
    if out_path is None:
        if out_dir is None:
            out_dir = lay.exports
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if created_ts is None:
            date_str = "unknown_date"
        else:
            dt = datetime.fromtimestamp(float(created_ts), tz=timezone.utc)
            date_str = dt.strftime("%Y%m%d")

        out_path = out_dir / f"{session_id}__export_{et}__{date_str}.zip"

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    entries = _build_entries_for_session(
        session_id,
        export_type=et,
        transcript_formats=transcript_formats,
        formalization_formats=formalization_formats,
    )

    items = sorted(entries.items(), key=lambda t: t[0])
    with zipfile.ZipFile(out_path, mode="x", compression=zipfile.ZIP_DEFLATED) as z:
        for arc, data in items:
            arc_path = Path(arc)
            if arc_path.is_absolute() or ".." in arc_path.parts:
                continue
            zi = zipfile.ZipInfo(filename=arc, date_time=_DETERMINISTIC_ZIP_DT)
            zi.external_attr = (0o644 & 0xFFFF) << 16
            z.writestr(zi, data)

    return ExportBundleResult(session_id=session_id, zip_path=str(out_path), files_added=len(items))


def _collect_run_files(run_id: str) -> tuple[str, list[Path]]:
    """Collect files for a single run bundle (v1).

    Includes:
    - session.json (+ optional session_state.json)
    - overlays for session (speaker_map)
    - contribution referenced by resolved_input receipt when available
    - run.json + events.jsonl
    - run artifacts/, exports/, inputs/

    This is deterministic and does not mutate the store.
    """
    lay = init_stuart_root()

    run_dir = lay.runs / run_id
    run_json = run_dir / "run.json"
    if not run_json.exists():
        raise FileNotFoundError(f"Unknown run_id (missing manifest): {run_json}")

    run_m = load_manifest(run_json)
    session_id = run_m.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError(f"Run manifest missing session_id: {run_json}")

    out: list[Path] = []

    # Session manifests
    sess_dir = lay.sessions / session_id
    out.append(sess_dir / "session.json")
    st = sess_dir / "session_state.json"
    if st.exists():
        out.append(st)

    # Overlays
    ovr_dir = lay.overlays / session_id
    if ovr_dir.exists():
        out.extend([p for p in _iter_files_recursive(ovr_dir)])

    # Contribution: prefer resolved_input receipt
    contrib_id: str | None = None
    resolved_path = run_dir / "inputs" / "resolved_input.json"
    if resolved_path.exists():
        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
            v = payload.get("contribution_id")
            if isinstance(v, str) and v.strip():
                contrib_id = v.strip()
        except Exception:
            contrib_id = None

    if contrib_id is not None:
        con_dir = lay.contributions / contrib_id
        man = con_dir / "contribution.json"
        if man.exists():
            out.append(man)
            for p in sorted(con_dir.iterdir()):
                if p.is_file() and p.name != "contribution.json":
                    out.append(p)
    else:
        # Fallback: include all contributions for session_id
        if lay.contributions.exists():
            for con_dir in sorted(lay.contributions.iterdir()):
                if not con_dir.is_dir():
                    continue
                man = con_dir / "contribution.json"
                if not man.exists():
                    continue
                try:
                    c = load_manifest(man)
                except Exception:
                    continue
                if c.get("session_id") != session_id:
                    continue
                out.append(man)
                for p in sorted(con_dir.iterdir()):
                    if p.is_file() and p.name != "contribution.json":
                        out.append(p)

    # Run core files
    out.append(run_json)
    ev = run_dir / "events.jsonl"
    if ev.exists():
        out.append(ev)

    # Run subdirs
    for sub in ("artifacts", "exports", "inputs"):
        d = run_dir / sub
        if d.exists():
            out.extend(list(_iter_files_recursive(d)))

    return session_id, [p for p in out if p.exists() and p.is_file()]


def export_run_bundle(
    run_id: str,
    *,
    out_dir: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> ExportBundleResult:
    lay = init_stuart_root()

    session_id, files = _collect_run_files(run_id)

    run_json = lay.runs / run_id / "run.json"
    run_m = load_manifest(run_json)
    created_ts = run_m.get("created_ts")
    if not isinstance(created_ts, (int, float)):
        created_ts = None

    if out_path is None:
        if out_dir is None:
            out_dir = lay.exports
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if created_ts is None:
            date_str = "unknown_date"
        else:
            dt = datetime.fromtimestamp(float(created_ts), tz=timezone.utc)
            date_str = dt.strftime("%Y%m%d")

        out_path = out_dir / f"{session_id}__run_bundle__{run_id}__{date_str}.zip"

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    root = lay.root
    items: List[Tuple[Path, str]] = []
    for p in files:
        rel = _safe_rel(root, p)
        if not rel:
            continue
        if rel.startswith("exports/"):
            continue
        items.append((p, rel))

    items.sort(key=lambda t: t[1])
    deduped: List[Tuple[Path, str]] = []
    seen = set()
    for src, arc in items:
        if arc in seen:
            continue
        seen.add(arc)
        deduped.append((src, arc))

    with zipfile.ZipFile(out_path, mode="x", compression=zipfile.ZIP_DEFLATED) as z:
        for src, arc in deduped:
            data = src.read_bytes()
            zi = zipfile.ZipInfo(filename=arc, date_time=_DETERMINISTIC_ZIP_DT)
            zi.external_attr = (0o644 & 0xFFFF) << 16
            z.writestr(zi, data)

    return ExportBundleResult(session_id=session_id, run_id=run_id, zip_path=str(out_path), files_added=len(deduped))
