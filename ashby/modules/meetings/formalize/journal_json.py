from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ashby.core.profile import ExecutionProfile, get_execution_profile
from ashby.modules.llm import HTTPGatewayLLMService, LLMFormalizeRequest
from ashby.modules.llm.service import TemplateSectionPayload, TranscriptSegmentPayload
from ashby.modules.meetings.formalize.llm_evidence_map import persist_llm_evidence_map
from ashby.modules.meetings.formalize.llm_text_sanitizer import sanitize_llm_text_fields
from ashby.modules.meetings.formalize.llm_usage_receipt import write_llm_usage_receipt
from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.overlays import load_speaker_map_overlay
from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.schemas.journal_v1 import validate_journal_v1
from ashby.modules.meetings.session_state import load_session_state
from ashby.modules.meetings.template_registry import load_template_spec, validate_template


_REMOTE_ENV_FLAG = "ASHBY_MEETINGS_LLM_ENABLED"


def _load_transcript_segments(run_dir: Path) -> Tuple[str, str, List[Dict[str, Any]], Optional[str]]:
    """Load transcript segments with segment_id anchors.

    Preference:
    - aligned_transcript.json (speaker-tagged) if present
    - transcript.json otherwise

    Returns (session_id, run_id, segments, transcript_version_id).
    """
    artifacts = run_dir / "artifacts"
    ajson = artifacts / "aligned_transcript.json"
    tjson = artifacts / "transcript.json"

    src = ajson if ajson.exists() else tjson
    if not src.exists():
        raise FileNotFoundError(f"Transcript JSON missing (need aligned_transcript.json or transcript.json): {src}")

    payload = json.loads(src.read_text(encoding="utf-8"))
    session_id = str(payload.get("session_id") or "")
    # QUEST_070: run_id is the *current* run directory id.
    # We may reuse transcript artifacts from a prior run; the transcript payload's run_id
    # is treated as source metadata and must not leak into newly-derived outputs.
    run_id = run_dir.name
    segs = list(payload.get("segments") or [])
    transcript_version_id = payload.get("transcript_version_id")
    trv = str(transcript_version_id).strip() if isinstance(transcript_version_id, str) else None
    return (session_id, run_id, segs, trv)


def _segment_id_set(segs: List[Dict[str, Any]]) -> Set[int]:
    out: Set[int] = set()
    for i, s in enumerate(segs):
        try:
            out.add(int(s.get("segment_id", i)))
        except Exception:
            continue
    return out


def _enabled_remote_llm() -> bool:
    v = (os.environ.get(_REMOTE_ENV_FLAG) or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _load_active_speaker_map(session_id: str) -> Dict[str, str]:
    st = load_session_state(session_id)
    overlay_id = st.get("active_speaker_overlay_id")
    if not isinstance(overlay_id, str) or not overlay_id.strip():
        return {}
    return load_speaker_map_overlay(session_id, overlay_id.strip())


def _as_transcript_segments_payload(segs: List[Dict[str, Any]], speaker_map: Dict[str, str]) -> List[TranscriptSegmentPayload]:
    payload: List[TranscriptSegmentPayload] = []
    for i, seg in enumerate(segs):
        sid = str(seg.get("segment_id", i))
        speaker_label = str(seg.get("speaker") or "SPEAKER_00")
        speaker_name = speaker_map.get(speaker_label)
        payload.append(
            TranscriptSegmentPayload(
                segment_id=sid,
                start_ms=int(seg.get("start_ms", 0)),
                end_ms=int(seg.get("end_ms", 0)),
                speaker_label=speaker_label,
                speaker_name=speaker_name if isinstance(speaker_name, str) and speaker_name.strip() else None,
                text=str(seg.get("text") or ""),
            )
        )
    return payload


def _apply_output_metadata(
    payload: Dict[str, Any],
    *,
    template_id: str,
    template_version: str,
    template_title: str,
    retention: str,
    include_citations: bool,
    show_empty_sections: bool,
    transcript_version_id: Optional[str],
) -> None:
    payload["template_id"] = template_id
    payload["template_version"] = template_version
    payload["template_title"] = template_title
    payload["retention"] = retention
    payload["include_citations"] = bool(include_citations)
    payload["show_empty_sections"] = bool(show_empty_sections)
    if transcript_version_id:
        payload["transcript_version_id"] = transcript_version_id


def _write_text_write_once(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite artifact: {path}")
    path.write_text(text, encoding="utf-8")


def _write_failure_receipt(run_dir: Path, *, stage: str, error: str, detail: Optional[Dict[str, Any]] = None) -> Path:
    """Write a loud failure receipt in artifacts/ (write-once)."""
    artifacts = run_dir / "artifacts"
    out = artifacts / f"{stage}_failure.json"
    payload: Dict[str, Any] = {
        "stage": stage,
        "error": error,
        "created_ts": time.time(),
    }
    if detail:
        payload["detail"] = detail
    dump_json(out, payload, write_once=True)
    return out


def _deterministic_journal_payload(
    *,
    session_id: str,
    run_id: str,
    segs: List[Dict[str, Any]],
    template_id: str,
    retention: str,
) -> Dict[str, Any]:
    """LOCAL_ONLY deterministic fallback.

    Truth discipline:
    - Do NOT invent events, action items, or key points.
    - Provide a readable, transcript-backed narrative section.
    """
    # Build a single narrative section (bounded length, evidence anchored).
    lines: List[str] = []
    anchors: List[Dict[str, Any]] = []

    for i, s in enumerate(segs):
        sid = int(s.get("segment_id", i))
        spk = str(s.get("speaker") or "SPEAKER_00")
        txt = str(s.get("text") or "").strip()
        if not txt:
            continue
        lines.append(f"{spk}: {txt}")
        anchors.append({"segment_id": sid})

    if not lines:
        lines = ["(No transcript text available.)"]
        anchors = [{"segment_id": 0}]

    # Keep citations bounded so we don't blow up small UIs.
    bounded_anchors = anchors[: min(len(anchors), 50)]

    payload: Dict[str, Any] = {
        "version": 1,
        "session_id": session_id,
        "run_id": run_id,
        "header": {
            "title": "Journal Entry",
            "mode": "journal",
            "retention": retention,
            "template_id": template_id,
            "created_ts": time.time(),
            "engine": "deterministic_fallback_v1",
        },
        "narrative_sections": [
            {
                "section_id": "sec_001",
                "title": "Transcript",
                "text": "\n".join(lines),
                # We include citations for the deterministic transcript-backed section (truth-first).
                "citations": bounded_anchors,
            }
        ],
        "key_points": [],
        "action_items": [],
        "feelings": [],
        "mood": "",
    }
    return payload


def _assert_citations_reference_real_segments(payload: Dict[str, Any], valid_ids: Set[int]) -> None:
    """Truth guard: any citations present must reference existing segment_id values."""

    def check_section(section: Any) -> None:
        if not isinstance(section, dict):
            return
        cites = section.get("citations")
        if cites is None:
            return
        if not isinstance(cites, list):
            return
        for c in cites:
            if not isinstance(c, dict):
                continue
            if "segment_id" not in c:
                continue
            sid = int(c["segment_id"])
            if sid not in valid_ids:
                raise ValueError(f"narrative_section cites unknown segment_id: {sid}")

    def check_list(items: Any, *, item_name: str) -> None:
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            cites = it.get("citations")
            if cites is None:
                continue
            if not isinstance(cites, list):
                continue
            for c in cites:
                if not isinstance(c, dict):
                    continue
                if "segment_id" not in c:
                    continue
                sid = int(c["segment_id"])
                if sid not in valid_ids:
                    raise ValueError(f"{item_name} cites unknown segment_id: {sid}")

    for s in payload.get("narrative_sections") or []:
        check_section(s)

    check_list(payload.get("key_points"), item_name="key_point")
    check_list(payload.get("action_items"), item_name="action_item")
    check_list(payload.get("feelings"), item_name="feeling")


def formalize_journal_to_journal_json(
    run_dir: Path,
    template_id: str,
    retention: str,
    *,
    template_version: Optional[str] = None,
    include_citations: Optional[bool] = None,
    show_empty_sections: Optional[bool] = None,
) -> Dict[str, Any]:
    """Produce artifacts/journal.json (v1) for journal mode.

    Profile gating:
    - LOCAL_ONLY: deterministic fallback only
    - HYBRID/CLOUD: remote LLM allowed only when ASHBY_MEETINGS_LLM_ENABLED is set.
      If remote unavailable, fall back deterministically.
      If remote returns invalid/non-JSON/schema-invalid, FAIL loudly and write receipts.

    Returns an artifact dict suitable for update_run_state().
    """
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    out_path = artifacts / "journal.json"
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite journal.json: {out_path}")

    tv = validate_template("journal", template_id)
    if not tv.ok or tv.template_id is None:
        raise ValueError(tv.message or "Invalid journal template.")
    spec = load_template_spec("journal", tv.template_id, version=template_version)

    session_id, run_id, segs, transcript_version_id = _load_transcript_segments(run_dir)
    valid_seg_ids = _segment_id_set(segs)
    speaker_map = _load_active_speaker_map(session_id)
    transcript_segments = _as_transcript_segments_payload(segs, speaker_map)
    template_sections = [
        TemplateSectionPayload(heading=section.heading, target_key=section.section_id, order=idx + 1)
        for idx, section in enumerate(spec.sections)
    ]
    resolved_include_citations = (
        bool(include_citations) if isinstance(include_citations, bool) else bool(spec.defaults.get("include_citations"))
    )
    resolved_show_empty_sections = (
        bool(show_empty_sections) if isinstance(show_empty_sections, bool) else bool(spec.defaults.get("show_empty_sections"))
    )

    profile = get_execution_profile()

    # LOCAL_ONLY => deterministic always
    if profile == ExecutionProfile.LOCAL_ONLY:
        payload = _deterministic_journal_payload(
            session_id=session_id,
            run_id=run_id,
            segs=segs,
            template_id=tv.template_id,
            retention=retention,
        )
        if transcript_version_id:
            payload["transcript_version_id"] = transcript_version_id
            payload.setdefault("header", {})["transcript_version_id"] = transcript_version_id
        _apply_output_metadata(
            payload,
            template_id=tv.template_id,
            template_version=spec.template_version,
            template_title=spec.template_title,
            retention=retention,
            include_citations=resolved_include_citations,
            show_empty_sections=resolved_show_empty_sections,
            transcript_version_id=transcript_version_id,
        )
        validate_journal_v1(payload)
        _assert_citations_reference_real_segments(payload, valid_seg_ids)
        dump_json(out_path, payload, write_once=True)
        return {
            "kind": "journal_json",
            "path": str(out_path),
            "sha256": sha256_file(out_path),
            "created_ts": time.time(),
            "engine": "deterministic_fallback_v1",
        }

    # HYBRID/CLOUD only attempt remote LLM when explicitly enabled
    if not _enabled_remote_llm():
        payload = _deterministic_journal_payload(
            session_id=session_id,
            run_id=run_id,
            segs=segs,
            template_id=tv.template_id,
            retention=retention,
        )
        if transcript_version_id:
            payload["transcript_version_id"] = transcript_version_id
            payload.setdefault("header", {})["transcript_version_id"] = transcript_version_id
        _apply_output_metadata(
            payload,
            template_id=tv.template_id,
            template_version=spec.template_version,
            template_title=spec.template_title,
            retention=retention,
            include_citations=resolved_include_citations,
            show_empty_sections=resolved_show_empty_sections,
            transcript_version_id=transcript_version_id,
        )
        validate_journal_v1(payload)
        _assert_citations_reference_real_segments(payload, valid_seg_ids)
        dump_json(out_path, payload, write_once=True)
        return {
            "kind": "journal_json",
            "path": str(out_path),
            "sha256": sha256_file(out_path),
            "created_ts": time.time(),
            "engine": "deterministic_fallback_v1",
            "warning": f"remote LLM disabled ({_REMOTE_ENV_FLAG} not set)",
        }

    transcript_text = "\n".join(
        str(s.get("text") or "").strip() for s in segs if str(s.get("text") or "").strip()
    )
    service = HTTPGatewayLLMService()
    request = LLMFormalizeRequest(
        transcript_text=transcript_text,
        transcript_segments=transcript_segments,
        mode="journal",
        template_id=tv.template_id,
        retention=retention,
        profile=profile.value,
        template_text=spec.raw_text,
        template_sections=template_sections,
        include_citations=resolved_include_citations,
        show_empty_sections=resolved_show_empty_sections,
    )
    try:
        gateway_resp = service.formalize(request, artifacts_dir=artifacts)
    except Exception as e:
        # Remote unavailable: fall back, but record warning in header.
        fail = _write_failure_receipt(
            run_dir,
            stage="journal_llm",
            error="gateway_formalize_failed",
            detail={"exception": f"{type(e).__name__}: {e}"},
        )
        payload = _deterministic_journal_payload(
            session_id=session_id,
            run_id=run_id,
            segs=segs,
            template_id=tv.template_id,
            retention=retention,
        )
        payload.get("header", {})["warning"] = f"remote formalizer unavailable: {type(e).__name__}: {e}"
        if transcript_version_id:
            payload["transcript_version_id"] = transcript_version_id
            payload.setdefault("header", {})["transcript_version_id"] = transcript_version_id
        _apply_output_metadata(
            payload,
            template_id=tv.template_id,
            template_version=spec.template_version,
            template_title=spec.template_title,
            retention=retention,
            include_citations=resolved_include_citations,
            show_empty_sections=resolved_show_empty_sections,
            transcript_version_id=transcript_version_id,
        )
        validate_journal_v1(payload)
        _assert_citations_reference_real_segments(payload, valid_seg_ids)
        dump_json(out_path, payload, write_once=True)
        return {
            "kind": "journal_json",
            "path": str(out_path),
            "sha256": sha256_file(out_path),
            "created_ts": time.time(),
            "engine": "deterministic_fallback_v1",
            "warning": f"{payload.get('header', {}).get('warning') or ''}; receipt={fail}",
        }

    raw_path = artifacts / "journal_llm_raw.txt"
    _write_text_write_once(
        raw_path,
        json.dumps(
            {
                "version": gateway_resp.version,
                "request_id": gateway_resp.request_id,
                "output_json": gateway_resp.output_json,
                "evidence_map": gateway_resp.evidence_map,
                "usage": gateway_resp.usage,
                "timing_ms": gateway_resp.timing_ms,
                "provider": gateway_resp.provider,
                "model": gateway_resp.model,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )
    if not isinstance(gateway_resp.output_json, dict):
        fail = _write_failure_receipt(
            run_dir,
            stage="journal_llm",
            error="gateway_output_json_not_object",
            detail={"request_id": gateway_resp.request_id, "raw_path": str(raw_path)},
        )
        raise ValueError(f"Gateway output_json must be object; see {fail}")

    llm_payload = dict(gateway_resp.output_json)
    try:
        llm_payload = sanitize_llm_text_fields(llm_payload, mode="journal")
    except Exception as e:
        fail = _write_failure_receipt(
            run_dir,
            stage="journal_llm",
            error="json_string_sanitization_failed",
            detail={"exception": f"{type(e).__name__}: {e}"},
        )
        raise ValueError(f"Gateway journal text sanitization failed; see {fail}") from e
    try:
        persist_llm_evidence_map(artifacts_dir=artifacts, evidence_map=gateway_resp.evidence_map)
    except Exception as e:
        fail = _write_failure_receipt(
            run_dir,
            stage="journal_llm",
            error="evidence_map_validation_failed",
            detail={"exception": f"{type(e).__name__}: {e}"},
        )
        raise ValueError(f"Gateway evidence_map invalid; see {fail}") from e

    # Enforce canonical identity fields
    llm_payload["version"] = 1
    llm_payload["session_id"] = session_id
    llm_payload["run_id"] = run_id
    header = llm_payload.get("header")
    if not isinstance(header, dict):
        header = {}
        llm_payload["header"] = header
    header.setdefault("mode", "journal")
    header.setdefault("retention", retention)
    header.setdefault("template_id", tv.template_id)
    header.setdefault("created_ts", time.time())
    _apply_output_metadata(
        llm_payload,
        template_id=tv.template_id,
        template_version=spec.template_version,
        template_title=spec.template_title,
        retention=retention,
        include_citations=resolved_include_citations,
        show_empty_sections=resolved_show_empty_sections,
        transcript_version_id=transcript_version_id,
    )

    # Ensure presence of expected top-level keys for stability
    llm_payload.setdefault("narrative_sections", [])
    llm_payload.setdefault("key_points", [])
    llm_payload.setdefault("action_items", [])
    llm_payload.setdefault("feelings", [])
    llm_payload.setdefault("mood", "")

    try:
        if transcript_version_id:
            llm_payload["transcript_version_id"] = transcript_version_id
            llm_payload.setdefault("header", {})["transcript_version_id"] = transcript_version_id
        validate_journal_v1(llm_payload)
        _assert_citations_reference_real_segments(llm_payload, valid_seg_ids)
    except Exception as e:
        raw_path = artifacts / "journal_llm_raw.json"
        dump_json(raw_path, {"raw": llm_payload}, write_once=True)
        fail = _write_failure_receipt(
            run_dir,
            stage="journal_llm",
            error="schema_validation_failed",
            detail={"exception": f"{type(e).__name__}: {e}", "raw_path": str(raw_path)},
        )
        raise ValueError(f"LLM journal schema validation failed; see {raw_path} and {fail}") from e

    dump_json(out_path, llm_payload, write_once=True)
    write_llm_usage_receipt(
        artifacts_dir=artifacts,
        provider=gateway_resp.provider,
        model=gateway_resp.model,
        request_id=gateway_resp.request_id,
        timing_ms=gateway_resp.timing_ms,
        usage=gateway_resp.usage,
        retention=retention,
    )
    return {
        "kind": "journal_json",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "created_ts": time.time(),
        "engine": "llm_gateway",
        "provider": gateway_resp.provider,
        "model": gateway_resp.model,
    }
