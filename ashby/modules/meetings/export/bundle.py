from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.manifests import load_manifest


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
    """Return a normalized posix relative path inside the bundle.

    Rails:
    - bundle content MUST be under STUART_ROOT
    - we never include absolute paths
    """
    try:
        rel = p.resolve().relative_to(root.resolve())
    except Exception:
        return None
    return rel.as_posix()


def _iter_files_recursive(dir_path: Path) -> Iterable[Path]:
    for p in sorted(dir_path.rglob("*")):
        if p.is_file():
            yield p


def _collect_session_files(session_id: str) -> List[Path]:
    lay = init_stuart_root()
    root = lay.root

    out: List[Path] = []

    # Session manifests
    sess_dir = lay.sessions / session_id
    out.append(sess_dir / "session.json")
    st = sess_dir / "session_state.json"
    if st.exists():
        out.append(st)
    trv_root = sess_dir / "transcripts"
    if trv_root.exists():
        out.extend([p for p in _iter_files_recursive(trv_root)])

    # Overlays (speaker_map only for now)
    ovr_dir = lay.overlays / session_id
    if ovr_dir.exists():
        out.extend([p for p in _iter_files_recursive(ovr_dir)])

    # Contributions: scan and match session_id
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
            # Include all other files in the contribution dir (source, derived_audio, etc.)
            for p in sorted(con_dir.iterdir()):
                if p.is_file() and p.name != "contribution.json":
                    out.append(p)

    # Runs: scan and match session_id
    if lay.runs.exists():
        for run_dir in sorted(lay.runs.iterdir()):
            if not run_dir.is_dir():
                continue
            run_json = run_dir / "run.json"
            if not run_json.exists():
                continue
            try:
                r = load_manifest(run_json)
            except Exception:
                continue
            if r.get("session_id") != session_id:
                continue

            out.append(run_json)
            ev = run_dir / "events.jsonl"
            if ev.exists():
                out.append(ev)

            art_dir = run_dir / "artifacts"
            if art_dir.exists():
                out.extend(list(_iter_files_recursive(art_dir)))

            exp_dir = run_dir / "exports"
            if exp_dir.exists():
                out.extend(list(_iter_files_recursive(exp_dir)))

            inputs_dir = run_dir / "inputs"
            if inputs_dir.exists():
                out.extend(list(_iter_files_recursive(inputs_dir)))

    # Filter to files that exist (some optional paths above)
    return [p for p in out if p.exists() and p.is_file()]


def _include_rel_for_export_type(rel: str, export_type: str) -> bool:
    et = (export_type or "full_bundle").strip().lower()
    if et == "full_bundle":
        return True

    # Session manifests + mutable state + overlays are always included.
    if rel.startswith("sessions/") and (rel.endswith("/session.json") or rel.endswith("/session_state.json")):
        return True
    if rel.startswith("overlays/"):
        return True

    # Keep receipts to preserve provenance.
    if rel.endswith("/run.json") or rel.endswith("/events.jsonl") or rel.endswith("/inputs/resolved_input.json"):
        return True
    if rel.startswith("contributions/") and rel.endswith("/contribution.json"):
        return True

    name = Path(rel).name.lower()
    in_run_exports = rel.startswith("runs/") and "/exports/" in rel

    transcript_names = {
        "transcript.json",
        "aligned_transcript.json",
        "transcript.txt",
        "diarization.json",
        "normalized.wav",
        "index.jsonl",
    }
    formalization_names = {
        "minutes.md",
        "minutes.json",
        "minutes.pdf",
        "journal.md",
        "journal.json",
        "journal.pdf",
        "evidence_map.json",
    }

    if et == "transcript_only":
        if rel.startswith("sessions/") and "/transcripts/" in rel:
            return True
        if name in transcript_names:
            return True
        # include uploaded source files for transcript lineage
        if rel.startswith("contributions/") and not rel.endswith("/contribution.json"):
            return True
        return False

    if et == "formalization_only":
        # Keep transcript version lineage available for provenance.
        if rel.startswith("sessions/") and "/transcripts/" in rel:
            return True
        if name in formalization_names:
            return True
        if in_run_exports:
            return True
        return False

    # Unknown filter -> safest fallback is include all.
    return True


def export_session_bundle(
    session_id: str,
    *,
    export_type: str = "full_bundle",
    out_dir: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> ExportBundleResult:
    """Create a read-only zip bundle of a session's manifests + artifacts.

    Contract (D5 / QUEST_067):
    - returns a zip path
    - no mutation of canonical store

    Notes:
    - This is a minimal v1 export to unblock CLI usage.
    - A fuller spec lives in QUEST_074.

    Determinism rails:
    - files are written in sorted order
    - zip timestamps and perms are normalized
    - output path uses session created date (UTC) when not specified
    """
    lay = init_stuart_root()
    root = lay.root

    sess_json = lay.sessions / session_id / "session.json"
    if not sess_json.exists():
        raise FileNotFoundError(f"Unknown session_id (missing manifest): {sess_json}")

    sess = load_manifest(sess_json)
    created_ts = sess.get("created_ts")
    if not isinstance(created_ts, (int, float)):
        created_ts = None

    if out_path is None:
        if out_dir is None:
            out_dir = lay.exports
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if created_ts is None:
            # deterministic fallback: literal string (no current-time dependence)
            date_str = "unknown_date"
        else:
            dt = datetime.fromtimestamp(float(created_ts), tz=timezone.utc)
            date_str = dt.strftime("%Y%m%d")

        et = (export_type or "full_bundle").strip().lower()
        out_path = out_dir / f"{session_id}__export_{et}__{date_str}.zip"

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = _collect_session_files(session_id)

    items: List[Tuple[Path, str]] = []
    for p in files:
        rel = _safe_rel(root, p)
        if not rel:
            continue
        # Guard: never include exports/ (avoid recursive bundle of prior bundles)
        if rel.startswith("exports/"):
            continue
        if not _include_rel_for_export_type(rel, export_type=export_type):
            continue
        items.append((p, rel))

    # Deterministic ordering
    items.sort(key=lambda t: t[1])

    # Create zip without overwrite
    with zipfile.ZipFile(out_path, mode="x", compression=zipfile.ZIP_DEFLATED) as z:
        for src, arc in items:
            data = src.read_bytes()
            zi = zipfile.ZipInfo(filename=arc, date_time=_DETERMINISTIC_ZIP_DT)
            # Normalize perms (rw-r--r--)
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
            import json
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
    """Create a deterministic, read-only zip bundle for a single run.

    Naming: <session_id>__run_bundle__<run_id>__YYYYMMDD.zip

    Determinism rails match export_session_bundle.
    """
    lay = init_stuart_root()

    session_id, files = _collect_run_files(run_id)

    # Determine date string from run created_ts when available
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
            # never include prior export bundles
            continue
        items.append((p, rel))

    # Deterministic ordering, dedup by arcname
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
