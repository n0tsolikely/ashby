from __future__ import annotations
import json
import os

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.core.profile import get_execution_profile
from ashby.modules.meetings.adapters.adapter_matrix import get_meetings_adapter_matrix
from ashby.modules.meetings.input_resolver import resolve_input_contribution
from ashby.modules.meetings.store import get_run_state, update_run_state, sha256_file
from ashby.modules.meetings.primary_outputs import build_primary_outputs
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.pipeline.diarize import diarize_stub
from ashby.modules.meetings.pipeline.search import search_and_write_results
from ashby.modules.meetings.render.minutes_md import render_minutes_md
from ashby.modules.meetings.render.journal_md import render_journal_md
from ashby.modules.meetings.formalize.minutes_json import formalize_meeting_to_minutes_json
from ashby.modules.meetings.formalize.journal_json import formalize_journal_to_journal_json
from ashby.modules.meetings.render.evidence_map import build_evidence_map
from ashby.modules.meetings.render.export_pdf import export_pdf_stub
from ashby.modules.meetings.index import ingest_run
from ashby.modules.meetings.session_state import (
    load_session_state,
    set_active_speaker_overlay,
    set_active_transcript_version,
)
from ashby.modules.meetings.overlays import create_speaker_map_overlay, load_speaker_map_overlay
from ashby.modules.meetings.render.extract_only import extract_only_by_speaker
from ashby.modules.meetings.truth.gate import gate_formalized_output
from ashby.modules.meetings.transcript_versions import create_transcript_version, load_transcript_version


@dataclass(frozen=True)
class RunResult:
    ok: bool
    run_id: str
    status: str
    message: str


class RunCancelled(Exception):
    pass


def _steps_from_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        return []
    out: List[Dict[str, Any]] = []
    for s in steps:
        if isinstance(s, dict):
            out.append(s)
        else:
            out.append({"kind": str(s)})
    return out


def _step_kind(step: Dict[str, Any]) -> str:
    for k in ("kind", "name", "stage", "id"):
        v = step.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def _get_run_artifact_path(run_id: str, filename: str) -> Optional[Path]:
    lay = init_stuart_root()
    p = lay.runs / run_id / "artifacts" / filename
    return p if p.exists() else None


def _first_formalize_reuse_run_id(steps: List[Dict[str, Any]]) -> Optional[str]:
    """Return the first reuse_run_id found in a formalize step.

    This is used to skip heavy stages early (normalize/transcribe/diarize/align)
    when the run is a true formalize-only rerun.
    """
    for st in steps:
        try:
            if _step_kind(st) != "formalize":
                continue
            params = st.get("params") if isinstance(st, dict) else {}
            v = (params or {}).get("reuse_run_id")
            if isinstance(v, str) and v.strip():
                return v.strip()
        except Exception:
            continue
    return None


def _first_formalize_transcript_version_id(steps: List[Dict[str, Any]]) -> Optional[str]:
    for st in steps:
        try:
            if _step_kind(st) != "formalize":
                continue
            params = st.get("params") if isinstance(st, dict) else {}
            v = (params or {}).get("transcript_version_id")
            if isinstance(v, str) and v.strip():
                return v.strip()
        except Exception:
            continue
    return None


def _copy_file_write_once(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise FileExistsError(f"Refusing to overwrite artifact: {dst}")
    dst.write_bytes(src.read_bytes())


def _materialize_reused_transcripts(*, lay: Any, run_dir: Path, reuse_run_id: str) -> Dict[str, Any]:
    """Copy transcript artifacts from a prior run into the current run_dir.

    Truth rails:
    - No mutation of the source run.
    - Destination writes are write-once.
    - We copy JSON substrate first (transcript.json + aligned_transcript.json when present).
    """
    src_run_dir = lay.runs / reuse_run_id
    src_artifacts = src_run_dir / "artifacts"
    if not src_artifacts.exists():
        raise FileNotFoundError(f"reuse_run_id artifacts missing: {src_artifacts}")

    dst_artifacts = run_dir / "artifacts"
    dst_artifacts.mkdir(parents=True, exist_ok=True)

    copied: List[Dict[str, Any]] = []

    def maybe_copy(filename: str, *, kind: str) -> Optional[Path]:
        sp = src_artifacts / filename
        if not sp.exists():
            return None
        dp = dst_artifacts / filename
        _copy_file_write_once(sp, dp)
        copied.append(
            {
                "kind": kind,
                "filename": filename,
                "path": str(dp),
                "sha256": sha256_file(dp),
                "source_path": str(sp),
                "source_sha256": sha256_file(sp),
            }
        )
        return dp

    # Preferred substrate for formalize/indexing.
    tjson = maybe_copy("transcript.json", kind="transcript_json")
    ajson = maybe_copy("aligned_transcript.json", kind="aligned_transcript_json")
    # Legacy convenience (not required, but preserves older tooling expectations).
    ttxt = maybe_copy("transcript.txt", kind="transcript_txt")

    if tjson is None and ajson is None:
        raise FileNotFoundError(
            "reuse_run_id missing transcript substrate (need transcript.json or aligned_transcript.json)"
        )

    # Write a reuse receipt for auditability (write-once).
    receipt = run_dir / "inputs" / "reused_transcript.json"
    if receipt.exists():
        raise FileExistsError(f"Refusing to overwrite reuse receipt: {receipt}")

    payload = {
        "version": 1,
        "reuse_run_id": reuse_run_id,
        "copied": copied,
        "created_ts": time.time(),
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"receipt_path": str(receipt), "receipt_sha256": sha256_file(receipt), "copied": copied}


def _maybe_load_active_speaker_map(session_id: str) -> Dict[str, str]:
    st = load_session_state(session_id)
    ovr_id = st.get("active_speaker_overlay_id")
    if isinstance(ovr_id, str) and ovr_id:
        return load_speaker_map_overlay(session_id, ovr_id)
    return {}


def _load_transcript_segments_for_version(run_dir: Path) -> List[Dict[str, Any]]:
    artifacts = run_dir / "artifacts"
    preferred = artifacts / "aligned_transcript.json"
    fallback = artifacts / "transcript.json"
    src = preferred if preferred.exists() else fallback
    if not src.exists():
        raise FileNotFoundError("missing transcript substrate for transcript_version emission")
    payload = json.loads(src.read_text(encoding="utf-8"))
    segs = payload.get("segments")
    if not isinstance(segs, list):
        raise ValueError("invalid transcript substrate schema")
    return segs


def _load_transcript_segments_with_source(run_dir: Path) -> tuple[List[Dict[str, Any]], Path]:
    artifacts = run_dir / "artifacts"
    preferred = artifacts / "aligned_transcript.json"
    fallback = artifacts / "transcript.json"
    src = preferred if preferred.exists() else fallback
    if not src.exists():
        raise FileNotFoundError("missing transcript substrate for transcript_version emission")
    payload = json.loads(src.read_text(encoding="utf-8"))
    segs = payload.get("segments")
    if not isinstance(segs, list):
        raise ValueError("invalid transcript substrate schema")
    return segs, src


def _asr_strict_enabled() -> bool:
    raw = str(os.environ.get("ASHBY_ASR_STRICT") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _coerce_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None


def _normalize_segments_and_integrity_report(
    segments: List[Dict[str, Any]], *, strict_mode: bool, source_name: str
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    normalized: List[Dict[str, Any]] = []
    seen_ids: set[int] = set()
    has_positive_duration = False

    for i, seg in enumerate(list(segments or [])):
        row_in = seg if isinstance(seg, dict) else {}
        if not isinstance(seg, dict):
            issues.append(
                {"severity": "error", "code": "segment_not_object", "segment_index": i, "message": "segment is not an object"}
            )

        seg_id_raw = row_in.get("segment_id")
        seg_id = _coerce_int(seg_id_raw)
        if seg_id is None:
            seg_id = i
            issues.append(
                {
                    "severity": "warning",
                    "code": "segment_id_assigned",
                    "segment_index": i,
                    "message": "segment_id missing/non-integer; assigned deterministically",
                    "assigned_segment_id": seg_id,
                }
            )

        if seg_id in seen_ids:
            issues.append(
                {
                    "severity": "error",
                    "code": "duplicate_segment_id",
                    "segment_index": i,
                    "segment_id": seg_id,
                    "message": "segment_id must be unique",
                }
            )
        else:
            seen_ids.add(seg_id)

        start_raw = row_in.get("start_ms")
        end_raw = row_in.get("end_ms")
        start_ms = _coerce_int(start_raw)
        end_ms = _coerce_int(end_raw)

        if start_ms is None or end_ms is None:
            issues.append(
                {
                    "severity": "error",
                    "code": "invalid_timestamps",
                    "segment_index": i,
                    "message": "start_ms/end_ms must exist and be integers",
                }
            )
            start_ms = 0 if start_ms is None else start_ms
            end_ms = 0 if end_ms is None else end_ms

        if start_ms < 0:
            issues.append(
                {"severity": "error", "code": "negative_start_ms", "segment_index": i, "start_ms": start_ms, "message": "start_ms must be >= 0"}
            )
        if end_ms < start_ms:
            issues.append(
                {
                    "severity": "error",
                    "code": "end_before_start",
                    "segment_index": i,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "message": "end_ms must be >= start_ms",
                }
            )
        if end_ms > start_ms:
            has_positive_duration = True

        out_row: Dict[str, Any] = {
            "segment_id": seg_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": str(row_in.get("text") or ""),
        }
        if row_in.get("speaker") is not None:
            out_row["speaker"] = row_in.get("speaker")
        if row_in.get("confidence") is not None:
            out_row["confidence"] = row_in.get("confidence")
        normalized.append(out_row)

    expected_ids = list(range(len(normalized)))
    actual_ids = [int(r.get("segment_id") or 0) for r in normalized]
    if actual_ids != expected_ids:
        issues.append(
            {
                "severity": "warning",
                "code": "non_canonical_segment_ids",
                "message": "segment_id sequence is not canonical 0..n-1",
            }
        )

    if strict_mode and not has_positive_duration:
        issues.append(
            {
                "severity": "error",
                "code": "strict_requires_positive_duration",
                "message": "strict mode requires at least one segment with end_ms > start_ms",
            }
        )

    hard_errors = [i for i in issues if str(i.get("severity") or "").lower() == "error"]
    return {
        "version": 1,
        "ok": len(hard_errors) == 0,
        "issues": issues,
        "source": source_name,
        "segments_count": len(normalized),
        "created_ts": time.time(),
        "normalized_segments": normalized,
    }


def _write_transcript_integrity_report(run_dir: Path, report: Dict[str, Any]) -> Path:
    out_path = run_dir / "artifacts" / "transcript_integrity_report.json"
    if out_path.exists():
        return out_path
    payload = dict(report)
    payload.pop("normalized_segments", None)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def _enforce_strict_transcribe_rails(run_dir: Path, transcribe_artifact: Dict[str, Any], strict_mode: bool) -> None:
    if not strict_mode:
        return

    engine = str(transcribe_artifact.get("engine") or "").strip().lower()
    if not engine:
        json_path = run_dir / "artifacts" / "transcript.json"
        if json_path.exists():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                engine = str(payload.get("engine") or "").strip().lower()
            except Exception:
                engine = ""

    if engine == "stub":
        raise ValueError(
            "ASR strict mode failure: transcript came from stub engine. "
            "Set ASHBY_ASR_ENABLE=1 and install/configure faster-whisper to run real ASR."
        )


def _resolve_diarization_enabled(params: Dict[str, Any], *, default: bool = True) -> tuple[bool, Optional[int], str]:
    explicit = params.get("diarization_enabled")
    if isinstance(explicit, bool):
        speakers_raw = params.get("speakers") or params.get("speaker_count") or params.get("num_speakers")
        speakers_i = _coerce_int(speakers_raw) if speakers_raw is not None and str(speakers_raw).strip() != "" else None
        return explicit, speakers_i, "explicit"

    legacy = params.get("diarize")
    if isinstance(legacy, bool):
        speakers_raw = params.get("speakers") or params.get("speaker_count") or params.get("num_speakers")
        speakers_i = _coerce_int(speakers_raw) if speakers_raw is not None and str(speakers_raw).strip() != "" else None
        return legacy, speakers_i, "legacy_alias"

    speakers_raw = params.get("speakers") or params.get("speaker_count") or params.get("num_speakers")
    speakers_i = _coerce_int(speakers_raw) if speakers_raw is not None and str(speakers_raw).strip() != "" else None
    if speakers_i is not None:
        return speakers_i > 1, speakers_i, "speaker_inference"
    return bool(default), None, "default"


def _emit_transcript_version_for_run(*, run_id: str, session_id: str, run_dir: Path, diarization_enabled: bool) -> Dict[str, Any]:
    strict_mode = _asr_strict_enabled()
    segs, src = _load_transcript_segments_with_source(run_dir)
    report = _normalize_segments_and_integrity_report(segs, strict_mode=strict_mode, source_name=src.name)
    report_path = _write_transcript_integrity_report(run_dir, report)
    update_run_state(
        run_id,
        artifact={"kind": "transcript_integrity_report", "path": str(report_path), "sha256": sha256_file(report_path), "created_ts": time.time()},
    )
    if not bool(report.get("ok")):
        raise ValueError(f"Transcript integrity check failed; see {report_path}")

    normalized = list(report.get("normalized_segments") or [])
    if not bool(diarization_enabled):
        for row in normalized:
            row.pop("speaker", None)

    resolved_input = run_dir / "inputs" / "resolved_input.json"
    audio_ref: Dict[str, Any] = {}
    if resolved_input.exists():
        try:
            rp = json.loads(resolved_input.read_text(encoding="utf-8"))
            if isinstance(rp, dict):
                cid = rp.get("contribution_id")
                source_path = rp.get("source_path")
                source_kind = rp.get("source_kind")
                if isinstance(cid, str) and cid.strip():
                    audio_ref["contribution_id"] = cid.strip()
                if isinstance(source_path, str) and source_path.strip():
                    audio_ref["path"] = source_path.strip()
                if isinstance(source_kind, str) and source_kind.strip():
                    audio_ref["source_kind"] = source_kind.strip()
        except Exception:
            pass

    payload = create_transcript_version(
        session_id=session_id,
        run_id=run_id,
        segments=normalized,
        diarization_enabled=bool(diarization_enabled),
        asr_engine="default",
        audio_ref=audio_ref,
    )
    trv_id = str(payload.get("transcript_version_id") or "")
    if trv_id:
        set_active_transcript_version(session_id, trv_id)
    return payload


def _materialize_transcript_version_for_formalize(*, run_dir: Path, session_id: str, transcript_version_id: str) -> Dict[str, Any]:
    payload = load_transcript_version(session_id, transcript_version_id)
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    dst = artifacts / "transcript.json"
    if dst.exists():
        raise FileExistsError(f"Refusing to overwrite artifact: {dst}")
    dst_payload = {
        "version": 1,
        "session_id": session_id,
        "run_id": run_dir.name,
        "transcript_version_id": transcript_version_id,
        "segments": payload.get("segments") or [],
        "engine": payload.get("asr_engine") or "default",
    }
    dst.write_text(json.dumps(dst_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "kind": "transcript_from_version",
        "path": str(dst),
        "sha256": sha256_file(dst),
        "created_ts": time.time(),
        "transcript_version_id": transcript_version_id,
    }


def _cancel_receipt_path(run_dir: Path) -> Path:
    return run_dir / "inputs" / "cancel.json"


def _raise_if_cancelled(run_id: str, run_dir: Path) -> None:
    p = _cancel_receipt_path(run_dir)
    if not p.exists():
        return
    raise RunCancelled(f"Run cancelled by request: {run_id}")


def run_job(run_id: str) -> RunResult:
    """Execute a run plan deterministically.

    - Idempotent: do not rerun succeeded/failed runs.
    - No ground-truth mutation: overlays are append-only; session_state is pointer-only.
    """
    state = get_run_state(run_id)
    if state.get("status") in ("succeeded", "failed"):
        return RunResult(ok=True, run_id=run_id, status=str(state.get("status")), message="Run already completed.")

    session_id = state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return RunResult(ok=False, run_id=run_id, status="failed", message="Run missing session_id")

    plan = state.get("plan") if isinstance(state, dict) else {}
    steps = _steps_from_plan(plan)

    # QUEST_070: detect formalize-only reruns early so we can skip heavy stages.
    formalize_reuse_run_id = _first_formalize_reuse_run_id(steps)
    formalize_transcript_version_id = _first_formalize_transcript_version_id(steps)

    lay = init_stuart_root()
    run_dir = lay.runs / run_id


    # QUEST_032: execution profile + adapter matrix (LOCAL_ONLY default)
    profile = get_execution_profile()
    matrix = get_meetings_adapter_matrix(profile)

    # QUEST_031: resolve input contribution (explicit or latest) and persist receipt
    explicit_cid = None
    try:
        for st in steps:
            params = st.get("params") if isinstance(st, dict) else {}
            v = (params or {}).get("contribution_id")
            if isinstance(v, str) and v.strip():
                explicit_cid = v.strip()
                break
    except Exception:
        explicit_cid = None

    resolved = None
    if formalize_transcript_version_id is None and formalize_reuse_run_id is None:
        resolved = resolve_input_contribution(session_id=session_id, layout=lay, contribution_id=explicit_cid)

        inputs_dir = run_dir / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = inputs_dir / "resolved_input.json"
        if receipt_path.exists():
            raise FileExistsError(f"Refusing to overwrite resolved_input receipt: {receipt_path}")

        receipt_path.write_text(
            json.dumps(
                {
                    "contribution_id": resolved.contribution_id,
                    "source_path": str(resolved.source_path),
                    "source_kind": resolved.source_kind,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        update_run_state(
            run_id,
            artifact={
                "kind": "resolved_input",
                "path": str(receipt_path),
                "sha256": sha256_file(receipt_path),
                "created_ts": time.time(),
            },
        )
    # QUEST_034: normalize input via adapter matrix (writes artifacts/normalized.wav)
    # QUEST_070: when reuse_run_id is provided for formalize, we skip normalization because
    # the run will reuse transcript artifacts and will not need audio-derived stages.
    if formalize_reuse_run_id is None and formalize_transcript_version_id is None:
        assert resolved is not None
        a0 = matrix.normalize(run_dir, resolved.source_path)
        update_run_state(run_id, artifact=a0)
    else:
        update_run_state(
            run_id,
            artifact={
                "kind": "normalize_skipped",
                "reason": "reuse_run_id or transcript_version_id provided (formalize-only rerun)",
                "reuse_run_id": formalize_reuse_run_id,
                "transcript_version_id": formalize_transcript_version_id,
                "created_ts": time.time(),
            },
        )

    # QUEST_068: Record which speaker overlay (if any) was active when this run began.
    # This is a *reference* only; overlays are append-only artifacts and session_state is pointer-only.
    st0 = load_session_state(session_id)
    ovr0 = st0.get("active_speaker_overlay_id")
    if isinstance(ovr0, str) and ovr0.strip():
        ovr_id0 = ovr0.strip()
        overlay_path = lay.overlays / session_id / "speaker_map" / f"{ovr_id0}.json"
        if overlay_path.exists():
            update_run_state(
                run_id,
                artifact={
                    "kind": "speaker_map_overlay_active",
                    "overlay_id": ovr_id0,
                    "path": str(overlay_path),
                    "sha256": sha256_file(overlay_path),
                    "created_ts": time.time(),
                },
            )


    now = time.time()
    update_run_state(run_id, status="running", stage="running", progress=0, started_ts=now)

    try:
        _raise_if_cancelled(run_id, run_dir)
        if not steps:
            update_run_state(run_id, stage="complete", progress=100)
        else:
            # SIDE-QUEST_079: progress rails
            # Avoid misleading instant 90% jumps by updating progress at *step start*
            # and then advancing within long steps (formalize) with sub-stage updates.
            step_kinds = [_step_kind(s) for s in steps]
            n = len(steps)

            # Default: equal share of 0..90 across steps.
            bounds = [int((i / n) * 90) for i in range(n + 1)]

            # Common plan: validate -> formalize (2 steps). Validate should not claim ~45%.
            if n == 2 and step_kinds[0] == "validate" and step_kinds[1] == "formalize":
                bounds = [0, 5, 90]

            # Rail: last bound must land at 90
            bounds[-1] = 90

            for i, step in enumerate(steps):
                _raise_if_cancelled(run_id, run_dir)
                kind = _step_kind(step)
                start_pct = int(bounds[i])
                end_pct = int(bounds[i + 1])
                step_label = kind or f"step_{i+1}"

                # Step-start state (prevents "jump-to-end" feel)
                update_run_state(run_id, stage=step_label, progress=start_pct)

                params = step.get("params") if isinstance(step, dict) else {}

                def _substage(label: str, idx: int, total: int) -> None:
                    """Update stage/progress within a step.

                    Progress is clamped to [start_pct, end_pct] and monotonic.
                    """
                    if not label:
                        label = step_label
                    if total <= 0:
                        update_run_state(run_id, stage=label, progress=start_pct)
                        return
                    frac = max(min(float(idx) / float(total), 1.0), 0.0)
                    pct = start_pct + int(frac * float(end_pct - start_pct))
                    if pct > end_pct:
                        pct = end_pct
                    update_run_state(run_id, stage=label, progress=pct)

                if kind == "validate":
                    # no-op: plan validation happens before run creation (kept for plan determinism)
                    pass

                if kind == "speaker_map_overlay":
                    overlay = (params or {}).get("overlay")
                    if not isinstance(overlay, dict) or not overlay:
                        raise ValueError("speaker_map_overlay missing overlay mapping")
                    mapping: Dict[str, str] = {}
                    for k, v in overlay.items():
                        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                            mapping[k.strip().upper()] = v.strip()
                    if not mapping:
                        raise ValueError("speaker_map_overlay mapping empty")
                    ovr = create_speaker_map_overlay(session_id, mapping)
                    set_active_speaker_overlay(session_id, ovr["overlay_id"])
                    update_run_state(
                        run_id,
                        artifact={
                            "kind": "speaker_map_overlay",
                            "overlay_id": ovr["overlay_id"],
                            "path": ovr["path"],
                            "sha256": ovr["sha256"],
                            "created_ts": ovr["created_ts"],
                            # Include mapping for auditability; transcript remains immutable.
                            "mapping": dict(ovr.get("mapping") or {}),
                        },
                    )

                elif kind == "formalize":
                    _raise_if_cancelled(run_id, run_dir)
                    # QUEST_070: true formalize-only rerun.
                    # If caller provides reuse_run_id, we reuse transcript.json/aligned_transcript.json
                    # from the prior run and skip audio-derived heavy stages.
                    reuse_raw = (params or {}).get("reuse_run_id")
                    reuse_run_id = reuse_raw.strip() if isinstance(reuse_raw, str) and reuse_raw.strip() else None
                    selected_trv_raw = (params or {}).get("transcript_version_id")
                    selected_trv = (
                        selected_trv_raw.strip()
                        if isinstance(selected_trv_raw, str) and selected_trv_raw.strip()
                        else None
                    )
                    if selected_trv is None:
                        st_for_trv = load_session_state(session_id)
                        active_trv = st_for_trv.get("active_transcript_version_id")
                        if isinstance(active_trv, str) and active_trv.strip():
                            selected_trv = active_trv.strip()
                    did_reuse = False
                    consumed_transcript_version_id: Optional[str] = None
                    produced_diarization_enabled = False

                    # Sub-stage plan for UI visibility (web/telegram).
                    mode = (params or {}).get("mode") or "meeting"
                    sub_labels: list[str] = []
                    if reuse_run_id is not None:
                        sub_labels.append("reuse_transcripts")
                    else:
                        sub_labels.append("transcribe")

                    if mode != "journal" and reuse_run_id is None:
                        sub_labels.extend(["diarize", "align"])
                    sub_labels.append("fts_ingest")
                    sub_labels.append("formalize_json")
                    sub_labels.append("truth_gate")
                    sub_labels.append("render_md")
                    sub_labels.append("evidence_map")
                    sub_labels.append("render_pdf")

                    sub_total = max(len(sub_labels), 1)
                    sub_i = 0

                    def bump(label: str) -> None:
                        nonlocal sub_i
                        _substage(label, sub_i, sub_total)
                        sub_i = min(sub_i + 1, sub_total)

                    # Start-of-formalize visibility (prevents UI from looking stalled)
                    _substage("formalize", 0, sub_total)

                    if reuse_run_id is not None:
                        did_reuse = True
                        bump("reuse_transcripts")
                        reused = _materialize_reused_transcripts(lay=lay, run_dir=run_dir, reuse_run_id=reuse_run_id)

                        # Receipt artifact (auditable link to source run)
                        update_run_state(
                            run_id,
                            artifact={
                                "kind": "reused_transcript_receipt",
                                "path": reused["receipt_path"],
                                "sha256": reused["receipt_sha256"],
                                "created_ts": time.time(),
                                "reuse_run_id": reuse_run_id,
                            },
                        )

                        # Record copied transcript substrates as artifacts so downstream components
                        # can resolve them deterministically.
                        for c in reused.get("copied") or []:
                            if not isinstance(c, dict):
                                continue
                            fn = c.get("filename")
                            pth = c.get("path")
                            sha = c.get("sha256")
                            if not isinstance(fn, str) or not isinstance(pth, str) or not isinstance(sha, str):
                                continue
                            if fn == "aligned_transcript.json":
                                update_run_state(
                                    run_id,
                                    artifact={
                                        "kind": "aligned_transcript",
                                        "path": pth,
                                        "sha256": sha,
                                        "created_ts": time.time(),
                                        "reuse_run_id": reuse_run_id,
                                    },
                                )
                            elif fn == "transcript.json":
                                # Mirror transcribe adapter fields (path + json_path) when possible.
                                ttxt_path = run_dir / "artifacts" / "transcript.txt"
                                update_run_state(
                                    run_id,
                                    artifact={
                                        "kind": "transcript",
                                        "path": str(ttxt_path) if ttxt_path.exists() else pth,
                                        "json_path": pth,
                                        "sha256": sha,
                                        "created_ts": time.time(),
                                        "engine": "reused",
                                        "reuse_run_id": reuse_run_id,
                                    },
                                    )

                    if not did_reuse and selected_trv is not None:
                        did_reuse = True
                        consumed_transcript_version_id = selected_trv
                        # Keep the session pointer aligned with explicit transcript selection.
                        set_active_transcript_version(session_id, selected_trv)
                        bump("reuse_transcripts")
                        tv_art = _materialize_transcript_version_for_formalize(
                            run_dir=run_dir,
                            session_id=session_id,
                            transcript_version_id=selected_trv,
                        )
                        update_run_state(run_id, artifact=tv_art)

                    if not did_reuse:
                        _raise_if_cancelled(run_id, run_dir)
                        bump("transcribe")
                        a1 = matrix.transcribe(run_dir)
                        _enforce_strict_transcribe_rails(run_dir, a1, _asr_strict_enabled())
                        update_run_state(run_id, artifact=a1)

                    # QUEST_042: stable run params
                    template_id = (params or {}).get("template_id") or (params or {}).get("template") or "default"
                    retention = (params or {}).get("retention") or "MED"

                    # QUEST_036: diarization policy
                    # - meeting mode: run diarization+alignment (real or stub, depending on availability)
                    # - journal mode: skip diarization by default
                    # QUEST_070: when did_reuse is True, we skip diarize+align entirely.
                    if mode != "journal" and not did_reuse:
                        diarization_enabled, speakers_i, diarization_source = _resolve_diarization_enabled((params or {}), default=True)
                        produced_diarization_enabled = bool(diarization_enabled)
                        if speakers_i is not None and speakers_i >= 2:
                            hint_path = run_dir / "inputs" / "speaker_hint.json"
                            if hint_path.exists():
                                raise FileExistsError(f"Refusing to overwrite speaker hint: {hint_path}")
                            hint_path.write_text(json.dumps({"speakers": speakers_i}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

                        if diarization_enabled:
                            _raise_if_cancelled(run_id, run_dir)
                            bump("diarize")
                            a2 = matrix.diarize(run_dir)
                            update_run_state(run_id, artifact=a2)
                            _raise_if_cancelled(run_id, run_dir)
                            bump("align")
                            a_align = matrix.align(run_dir)
                            update_run_state(run_id, artifact=a_align)
                        else:
                            update_run_state(
                                run_id,
                                artifact={
                                    "kind": "diarize_align_skipped",
                                    "reason": f"diarization disabled ({diarization_source})",
                                    "speakers": speakers_i,
                                    "diarization_source": diarization_source,
                                    "created_ts": time.time(),
                                },
                            )
                    elif mode != "journal" and did_reuse:
                        update_run_state(
                            run_id,
                            artifact={
                                "kind": "diarize_align_skipped",
                                "reason": "reuse_run_id provided (formalize-only rerun)",
                                "reuse_run_id": reuse_run_id,
                                "created_ts": time.time(),
                            },
                        )
                    elif mode == "journal":
                        produced_diarization_enabled = False

                    # QUEST_117: transcribe-stage transcript version emission.
                    # For meeting mode this runs after optional diarize/align so aligned substrate is preferred.
                    if not did_reuse:
                        _raise_if_cancelled(run_id, run_dir)
                        produced_tv = _emit_transcript_version_for_run(
                            run_id=run_id,
                            session_id=session_id,
                            run_dir=run_dir,
                            diarization_enabled=produced_diarization_enabled,
                        )
                        produced_tv_id = str(produced_tv.get("transcript_version_id") or "")
                        if produced_tv_id:
                            consumed_transcript_version_id = produced_tv_id
                            # Stamp local transcript substrate with the produced transcript version id
                            # so downstream formalize/evidence artifacts can carry provenance.
                            tjson = run_dir / "artifacts" / "transcript.json"
                            if tjson.exists():
                                try:
                                    tp = json.loads(tjson.read_text(encoding="utf-8"))
                                    if isinstance(tp, dict):
                                        tp["transcript_version_id"] = produced_tv_id
                                        tjson.write_text(json.dumps(tp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                                except Exception:
                                    pass
                            ajson = run_dir / "artifacts" / "aligned_transcript.json"
                            if ajson.exists():
                                try:
                                    ap = json.loads(ajson.read_text(encoding="utf-8"))
                                    if isinstance(ap, dict):
                                        ap["transcript_version_id"] = produced_tv_id
                                        ajson.write_text(json.dumps(ap, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                                except Exception:
                                    pass
                            update_run_state(
                                run_id,
                                artifact={
                                    "kind": "produced_transcript_version",
                                    "transcript_version_id": produced_tv_id,
                                    "created_ts": time.time(),
                                },
                            )

                    # QUEST_037 + QUEST_057: auto-ingest into SQLite FTS so search works without manual ingest.
                    # Prefer aligned_transcript.json when present (meeting mode) so speaker labels are preserved.
                    _raise_if_cancelled(run_id, run_dir)
                    bump("fts_ingest")
                    ingest_path = run_dir / "artifacts" / "fts_ingest.json"
                    if ingest_path.exists():
                        raise FileExistsError(f"Refusing to overwrite ingest receipt: {ingest_path}")
                    ingest_ok = True
                    ingest_err = ""
                    try:
                        ingest_run(run_id)
                    except Exception as e:
                        ingest_ok = False
                        ingest_err = f"{type(e).__name__}: {e}"
                    ingest_payload = {"version": 1, "run_id": run_id, "ok": ingest_ok, "error": ingest_err}
                    ingest_path.write_text(json.dumps(ingest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    update_run_state(run_id, artifact={"kind": "fts_ingest", "path": str(ingest_path), "sha256": sha256_file(ingest_path), "created_ts": time.time()})

                    bump("formalize_json")
                    _raise_if_cancelled(run_id, run_dir)
                    if mode == "meeting":
                        a_minutes = formalize_meeting_to_minutes_json(
                            run_dir,
                            template_id=template_id,
                            retention=retention,
                        )
                        update_run_state(run_id, artifact=a_minutes)
                    elif mode == "journal":
                        a_journal = formalize_journal_to_journal_json(
                            run_dir,
                            template_id=template_id,
                            retention=retention,
                        )
                        update_run_state(run_id, artifact=a_journal)

                    # SIDE-QUEST_077: TruthGateJudge + MeetingsTruthPolicy must run BEFORE MD/PDF publish.
                    bump("truth_gate")
                    _raise_if_cancelled(run_id, run_dir)
                    if mode not in ("meeting", "journal"):
                        raise ValueError(f"Unsupported mode for truth gate: {mode}")
                    tg_decision, tg_art = gate_formalized_output(
                        run_dir=run_dir,
                        session_id=session_id,
                        run_id=run_id,
                        mode=mode,
                    )
                    update_run_state(run_id, artifact=tg_art)
                    if tg_decision.blocked:
                        raise ValueError(f"Truth gate blocked formalized output; see {tg_art.get('path')}")

                    if consumed_transcript_version_id:
                        update_run_state(
                            run_id,
                            artifact={
                                "kind": "consumed_transcript_version",
                                "transcript_version_id": consumed_transcript_version_id,
                                "created_ts": time.time(),
                            },
                        )

                    # Mode-specific MD artifact naming (Codex contract)
                    bump("render_md")
                    _raise_if_cancelled(run_id, run_dir)
                    if mode == "meeting":
                        a3 = render_minutes_md(run_dir)
                        md_path = run_dir / "artifacts" / "minutes.md"
                    elif mode == "journal":
                        a3 = render_journal_md(run_dir)
                        md_path = run_dir / "artifacts" / "journal.md"
                    else:
                        raise ValueError(f"Unsupported mode for MD render: {mode}")
                    update_run_state(run_id, artifact=a3)
                    bump("evidence_map")
                    a4 = build_evidence_map(run_dir)
                    update_run_state(run_id, artifact=a4)
                    pdf_name = "minutes.pdf" if mode == "meeting" else "journal.pdf"
                    bump("render_pdf")
                    _raise_if_cancelled(run_id, run_dir)
                    a5 = matrix.pdf(run_dir, md_path=md_path, out_name=pdf_name)
                    update_run_state(run_id, artifact=a5)

                elif kind == "transcribe":
                    mode = str((params or {}).get("mode") or "meeting").strip().lower()
                    if mode not in {"meeting", "journal"}:
                        raise ValueError("transcribe mode must be meeting or journal")
                    diarization_enabled, _speakers_i, _source = _resolve_diarization_enabled((params or {}), default=True)

                    _raise_if_cancelled(run_id, run_dir)
                    a1 = matrix.transcribe(run_dir)
                    _enforce_strict_transcribe_rails(run_dir, a1, _asr_strict_enabled())
                    update_run_state(run_id, artifact=a1)

                    if mode == "meeting" and diarization_enabled:
                        _raise_if_cancelled(run_id, run_dir)
                        a2 = matrix.diarize(run_dir)
                        update_run_state(run_id, artifact=a2)
                        _raise_if_cancelled(run_id, run_dir)
                        a_align = matrix.align(run_dir)
                        update_run_state(run_id, artifact=a_align)
                    else:
                        update_run_state(
                            run_id,
                            artifact={
                                "kind": "diarize_align_skipped",
                                "reason": "diarization disabled by request" if mode == "meeting" else "journal mode",
                                "diarization_enabled": diarization_enabled,
                                "created_ts": time.time(),
                            },
                        )

                    _raise_if_cancelled(run_id, run_dir)
                    produced_tv = _emit_transcript_version_for_run(
                        run_id=run_id,
                        session_id=session_id,
                        run_dir=run_dir,
                        diarization_enabled=(mode == "meeting" and diarization_enabled),
                    )
                    produced_tv_id = str(produced_tv.get("transcript_version_id") or "")
                    if produced_tv_id:
                        update_run_state(
                            run_id,
                            artifact={
                                "kind": "produced_transcript_version",
                                "transcript_version_id": produced_tv_id,
                                "created_ts": time.time(),
                            },
                        )

                    _raise_if_cancelled(run_id, run_dir)
                    ingest_path = run_dir / "artifacts" / "fts_ingest.json"
                    if ingest_path.exists():
                        raise FileExistsError(f"Refusing to overwrite ingest receipt: {ingest_path}")
                    ingest_ok = True
                    ingest_err = ""
                    try:
                        ingest_run(run_id)
                    except Exception as e:
                        ingest_ok = False
                        ingest_err = f"{type(e).__name__}: {e}"
                    ingest_payload = {"version": 1, "run_id": run_id, "ok": ingest_ok, "error": ingest_err}
                    ingest_path.write_text(json.dumps(ingest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    update_run_state(
                        run_id,
                        artifact={"kind": "fts_ingest", "path": str(ingest_path), "sha256": sha256_file(ingest_path), "created_ts": time.time()},
                    )

                elif kind == "search":
                    q = (params or {}).get("query")
                    if not isinstance(q, str):
                        q = str(q) if q is not None else ""
                    sess_filter = (params or {}).get("session_id")
                    if sess_filter is None:
                        sess_filter = session_id
                    if isinstance(sess_filter, str) and sess_filter.strip() == "":
                        sess_filter = None
                    if sess_filter is not None and not isinstance(sess_filter, str):
                        sess_filter = str(sess_filter)
                    lim = (params or {}).get("limit", 10)
                    try:
                        lim_i = int(lim)
                    except Exception:
                        lim_i = 10
                    mode_filter = (params or {}).get("mode_filter")
                    if isinstance(mode_filter, str) and mode_filter.strip() == "":
                        mode_filter = None
                    if mode_filter is not None and not isinstance(mode_filter, str):
                        mode_filter = str(mode_filter)

                    a_search = search_and_write_results(run_dir, query=q, session_id=sess_filter, mode_filter=mode_filter, limit=lim_i)
                    update_run_state(run_id, artifact=a_search)

                elif kind == "extract_only":
                    who = (params or {}).get("query")
                    if not isinstance(who, str) or not who.strip():
                        raise ValueError("extract_only requires query (speaker name)")
                    # Determine speaker_label from active speaker map
                    if mode == "meeting":
                        a_minutes = formalize_meeting_to_minutes_json(
                            run_dir,
                            template_id=template_id,
                            retention=retention,
                        )
                        update_run_state(run_id, artifact=a_minutes)
                    elif mode == "journal":
                        a_journal = formalize_journal_to_journal_json(
                            run_dir,
                            template_id=template_id,
                            retention=retention,
                        )
                        update_run_state(run_id, artifact=a_journal)
                    speaker_map = _maybe_load_active_speaker_map(session_id)
                    # reverse mapping: name -> label
                    wanted = who.strip()
                    label = None
                    for k, v in speaker_map.items():
                        if v == wanted:
                            label = k
                            break
                    if label is None:
                        raise ValueError(f"No active speaker mapping for '{wanted}'. Set mapping first.")

                    # Prefer reusing transcript from last run if available
                    last_run_id = state.get("last_run_id") if isinstance(state.get("last_run_id"), str) else None
                    transcript_path = _get_run_artifact_path(last_run_id, "transcript.txt") if last_run_id else None
                    if transcript_path is None:
                        a1 = matrix.transcribe(run_dir)
                        update_run_state(run_id, artifact=a1)

                    out_dir = run_dir / "artifacts" / "extract_only"
                    ex = extract_only_by_speaker(out_dir=out_dir, transcript_path=transcript_path, speaker_label=label, speaker_name=wanted, speaker_map=speaker_map)
                    update_run_state(run_id, artifact={"kind": "extract_only", "path": ex["paths"]["json"], "sha256": ex["sha256"]["json"], "created_ts": ex["created_ts"]})
                    pdf = export_pdf_stub(run_dir, md_path=Path(ex["paths"]["md"]), out_name="extract_only.pdf")
                    update_run_state(run_id, artifact=pdf)

                # step-end state
                update_run_state(run_id, stage=step_label, progress=end_pct)

        end = time.time()
        final_state = get_run_state(run_id)
        po = build_primary_outputs(final_state)
        update_run_state(run_id, status="succeeded", stage="succeeded", progress=100, ended_ts=end, primary_outputs=po)
        return RunResult(ok=True, run_id=run_id, status="succeeded", message="Run completed.")
    except RunCancelled as e:
        end = time.time()
        cur = get_run_state(run_id)
        prog = cur.get("progress")
        try:
            prog_i = int(prog) if prog is not None else 0
        except Exception:
            prog_i = 0
        update_run_state(run_id, status="cancelled", stage="cancelled", progress=prog_i, ended_ts=end, error={"type": "RunCancelled", "message": str(e)})
        return RunResult(ok=False, run_id=run_id, status="cancelled", message=str(e))
    except Exception as e:
        end = time.time()
        err = {"type": e.__class__.__name__, "message": str(e)}
        # Don't rely on the initial `state` snapshot for progress; fetch the latest run.json.
        cur = get_run_state(run_id)
        prog = cur.get("progress")
        try:
            prog_i = int(prog) if prog is not None else 0
        except Exception:
            prog_i = 0
        update_run_state(run_id, status="failed", stage="failed", progress=prog_i, ended_ts=end, error=err)
        return RunResult(ok=False, run_id=run_id, status="failed", message=str(e))


def poll_progress(run_id: str) -> Dict[str, Any]:
    s = get_run_state(run_id)
    return {
        "run_id": run_id,
        "status": s.get("status"),
        "stage": s.get("stage"),
        "progress": s.get("progress"),
        "started_ts": s.get("started_ts"),
        "ended_ts": s.get("ended_ts"),
    }
