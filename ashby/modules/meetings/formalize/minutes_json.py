from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ashby.core.profile import ExecutionProfile, get_execution_profile
from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.schemas.minutes_v1 import validate_minutes_v1
from ashby.modules.meetings.template_registry import load_system_template_text, validate_template


_REMOTE_ENV_FLAG = "ASHBY_MEETINGS_LLM_ENABLED"
_DEFAULT_MODEL_ENV = "ASHBY_MEETINGS_FORMALIZER_MODEL"


def _load_transcript_segments(run_dir: Path) -> Tuple[str, str, List[Dict[str, Any]], Optional[str]]:
    """Load meeting transcript segments with segment_id anchors.

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

    # Deterministic fallback rail:
    # when transcript.json is stub-engine, prefer it over aligned output so
    # speaker-line granularity remains stable for golden tests and audit parity.
    if ajson.exists() and tjson.exists():
        try:
            t_payload = json.loads(tjson.read_text(encoding="utf-8"))
            if str(t_payload.get("engine") or "").strip().lower() == "stub":
                src = tjson
        except Exception:
            pass

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
    for s in segs:
        try:
            out.add(int(s.get("segment_id", 0)))
        except Exception:
            continue
    return out


def _enabled_remote_llm() -> bool:
    v = (os.environ.get(_REMOTE_ENV_FLAG) or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


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


def _deterministic_minutes_payload(
    *,
    session_id: str,
    run_id: str,
    segs: List[Dict[str, Any]],
    template_id: str,
    retention: str,
) -> Dict[str, Any]:
    """LOCAL_ONLY deterministic fallback.

    Truth discipline:
    - Do NOT invent decisions or action items.
    - Represent transcript content as evidence-backed notes (near-verbatim).
    """
    speakers: List[str] = []
    seen = set()
    for s in segs:
        spk = str(s.get("speaker") or "SPEAKER_00")
        if spk not in seen:
            seen.add(spk)
            speakers.append(spk)

    participants = [{"speaker_label": spk} for spk in speakers] if speakers else [{"speaker_label": "SPEAKER_00"}]

    # One topic that anchors to the whole transcript (auditable, minimal).
    all_anchors = [{"segment_id": int(s.get("segment_id", i))} for i, s in enumerate(segs) if "segment_id" in s or True]
    if not all_anchors:
        all_anchors = [{"segment_id": 0}]

    topics = [
        {
            "topic_id": "topic_001",
            "title": "Transcript",
            "summary": "Deterministic fallback: transcript-backed notes (no invented decisions/actions).",
            "citations": all_anchors[: min(len(all_anchors), 50)],  # keep bounded
        }
    ]

    notes: List[Dict[str, Any]] = []
    for i, s in enumerate(segs):
        sid = int(s.get("segment_id", i))
        spk = str(s.get("speaker") or "SPEAKER_00")
        text = str(s.get("text") or "").strip()
        if not text:
            continue
        notes.append(
            {
                "note_id": f"note_{sid:04d}",
                "text": f"{spk}: {text}",
                "citations": [{"segment_id": sid}],
            }
        )

    return {
        "version": 1,
        "session_id": session_id,
        "run_id": run_id,
        "header": {
            "title": "Meeting Minutes",
            "mode": "meeting",
            "retention": retention,
            "template_id": template_id,
            "created_ts": time.time(),
            "engine": "deterministic_fallback_v1",
        },
        "participants": participants,
        "topics": topics,
        "decisions": [],
        "action_items": [],
        "notes": notes,
        "open_questions": [],
    }


def _call_openai_minutes_json(*, system_prompt: str, user_prompt: str) -> str:
    """Remote formalization call (OpenAI).

    Note: This function is intentionally isolated for easy mocking in tests.
    """
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(f"openai package unavailable: {type(e).__name__}: {e}")

    model = (os.environ.get(_DEFAULT_MODEL_ENV) or "gpt-4o-mini").strip()
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Prefer JSON mode when supported; fall back if the client rejects the arg.
    kwargs: Dict[str, Any] = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    try:
        kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
    except TypeError:
        kwargs.pop("response_format", None)
        resp = client.chat.completions.create(**kwargs)  # type: ignore[arg-type]

    # OpenAI python lib returns objects; normalize to string
    msg = resp.choices[0].message
    content = msg.content if hasattr(msg, "content") else None
    if not isinstance(content, str):
        raise RuntimeError("OpenAI response missing message content")
    return content


def _assert_citations_reference_real_segments(payload: Dict[str, Any], valid_ids: Set[int]) -> None:
    """Truth guard: citations must reference existing segment_ids."""
    def check_list(items: Any, *, item_name: str) -> None:
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            cites = it.get("citations")
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

    check_list(payload.get("topics"), item_name="topic")
    check_list(payload.get("decisions"), item_name="decision")
    check_list(payload.get("action_items"), item_name="action_item")
    check_list(payload.get("notes"), item_name="note")
    check_list(payload.get("open_questions"), item_name="open_question")


def formalize_meeting_to_minutes_json(run_dir: Path, template_id: str, retention: str) -> Dict[str, Any]:
    """Produce artifacts/minutes.json (v1) for meeting mode.

    Profile gating:
    - LOCAL_ONLY: deterministic fallback only
    - HYBRID/CLOUD: remote LLM allowed only when ASHBY_MEETINGS_LLM_ENABLED is set.
      If remote unavailable, fall back deterministically.
      If remote returns invalid/non-JSON/schema-invalid, FAIL loudly and write receipts.

    Returns an artifact dict suitable for update_run_state().
    """
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    out_path = artifacts / "minutes.json"
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite minutes.json: {out_path}")

    # Template must be validated (prevents hallucinated template ids).
    tv = validate_template("meeting", template_id)
    if not tv.ok or tv.template_id is None:
        raise ValueError(tv.message or "Invalid meeting template.")

    session_id, run_id, segs, transcript_version_id = _load_transcript_segments(run_dir)
    valid_seg_ids = _segment_id_set(segs)

    profile = get_execution_profile()

    # LOCAL_ONLY => deterministic always
    if profile == ExecutionProfile.LOCAL_ONLY:
        payload = _deterministic_minutes_payload(
            session_id=session_id,
            run_id=run_id,
            segs=segs,
            template_id=tv.template_id,
            retention=retention,
        )
        if transcript_version_id:
            payload["transcript_version_id"] = transcript_version_id
            payload.setdefault("header", {})["transcript_version_id"] = transcript_version_id
        validate_minutes_v1(payload)
        dump_json(out_path, payload, write_once=True)
        return {
            "kind": "minutes_json",
            "path": str(out_path),
            "sha256": sha256_file(out_path),
            "created_ts": time.time(),
            "engine": "deterministic_fallback_v1",
        }

    # HYBRID/CLOUD only attempt remote LLM when explicitly enabled
    if not _enabled_remote_llm():
        payload = _deterministic_minutes_payload(
            session_id=session_id,
            run_id=run_id,
            segs=segs,
            template_id=tv.template_id,
            retention=retention,
        )
        if transcript_version_id:
            payload["transcript_version_id"] = transcript_version_id
            payload.setdefault("header", {})["transcript_version_id"] = transcript_version_id
        validate_minutes_v1(payload)
        dump_json(out_path, payload, write_once=True)
        return {
            "kind": "minutes_json",
            "path": str(out_path),
            "sha256": sha256_file(out_path),
            "created_ts": time.time(),
            "engine": "deterministic_fallback_v1",
            "warning": f"remote LLM disabled ({_REMOTE_ENV_FLAG} not set)",
        }

    # Remote path
    system_template = load_system_template_text("meeting", tv.template_id).strip()

    # We pass segments as JSON so the model can cite segment_id anchors truthfully.
    # NOTE: We deliberately avoid passing/allowing invented participant names.
    seg_compact = [
        {
            "segment_id": int(s.get("segment_id", i)),
            "speaker": str(s.get("speaker") or "SPEAKER_00"),
            "text": str(s.get("text") or "").strip(),
        }
        for i, s in enumerate(segs)
        if str(s.get("text") or "").strip()
    ]

    user_prompt = f"""You are generating Stuart meeting minutes.
Return ONLY valid JSON for the minutes.json v1 schema.

Rules:
- Do not invent attendees, names, decisions, or action items.
- If a decision or action item is not explicitly supported, omit it (use empty lists).
- Every topic/decision/action_item/note/open_question MUST include non-empty citations.
- Citations must be objects with segment_id referencing REAL segment_id values from the transcript.
- Assignee (if present) must be a speaker_label like SPEAKER_00; otherwise null.
- Include ALL top-level keys even if empty.

retention={retention}
template_id={tv.template_id}

Transcript segments (JSON array):
{json.dumps(seg_compact, indent=2, sort_keys=True)}
"""

    system_prompt = (
        "STUART FORMALIZER (minutes.json v1)\n"
        "You must follow the system template instructions, but output MUST be JSON only.\n\n"
        + system_template
    )

    try:
        raw = _call_openai_minutes_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception as e:
        # Remote unavailable: fall back, but record warning in header for transparency.
        payload = _deterministic_minutes_payload(
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
        validate_minutes_v1(payload)
        dump_json(out_path, payload, write_once=True)
        return {
            "kind": "minutes_json",
            "path": str(out_path),
            "sha256": sha256_file(out_path),
            "created_ts": time.time(),
            "engine": "deterministic_fallback_v1",
            "warning": str(payload.get("header", {}).get("warning") or ""),
        }

    # Parse strict JSON
    try:
        llm_payload = json.loads(raw)
    except Exception:
        raw_path = artifacts / "minutes_llm_raw.txt"
        _write_text_write_once(raw_path, raw)
        fail = _write_failure_receipt(run_dir, stage="minutes_llm", error="non_json_output", detail={"raw_path": str(raw_path)})
        raise ValueError(f"LLM returned non-JSON minutes output; see {raw_path} and {fail}")

    if not isinstance(llm_payload, dict):
        raw_path = artifacts / "minutes_llm_raw.txt"
        _write_text_write_once(raw_path, raw)
        fail = _write_failure_receipt(run_dir, stage="minutes_llm", error="json_not_object", detail={"raw_path": str(raw_path)})
        raise ValueError(f"LLM returned JSON but not an object; see {raw_path} and {fail}")

    # Enforce canonical identity fields (truthful; derived from runtime context)
    llm_payload["version"] = 1
    llm_payload["session_id"] = session_id
    llm_payload["run_id"] = run_id
    header = llm_payload.get("header")
    if not isinstance(header, dict):
        header = {}
        llm_payload["header"] = header
    header.setdefault("mode", "meeting")
    header.setdefault("retention", retention)
    header.setdefault("template_id", tv.template_id)
    header.setdefault("created_ts", time.time())

    # Validate schema and truth-guard citations
    try:
        if transcript_version_id:
            llm_payload["transcript_version_id"] = transcript_version_id
            llm_payload.setdefault("header", {})["transcript_version_id"] = transcript_version_id
        validate_minutes_v1(llm_payload)
        _assert_citations_reference_real_segments(llm_payload, valid_seg_ids)
    except Exception as e:
        raw_path = artifacts / "minutes_llm_raw.json"
        dump_json(raw_path, {"raw": llm_payload}, write_once=True)
        fail = _write_failure_receipt(
            run_dir,
            stage="minutes_llm",
            error="schema_validation_failed",
            detail={"exception": f"{type(e).__name__}: {e}", "raw_path": str(raw_path)},
        )
        raise ValueError(f"LLM minutes schema validation failed; see {raw_path} and {fail}") from e

    dump_json(out_path, llm_payload, write_once=True)
    return {
        "kind": "minutes_json",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "created_ts": time.time(),
        "engine": "openai",
        "model": (os.environ.get(_DEFAULT_MODEL_ENV) or "gpt-4o-mini").strip(),
    }
