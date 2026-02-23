from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ashby.core.profile import ExecutionProfile, get_execution_profile
from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.schemas.journal_v1 import validate_journal_v1
from ashby.modules.meetings.template_registry import load_system_template_text, validate_template


_REMOTE_ENV_FLAG = "ASHBY_MEETINGS_LLM_ENABLED"
_DEFAULT_MODEL_ENV = "ASHBY_MEETINGS_FORMALIZER_MODEL"


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


def _call_openai_journal_json(*, system_prompt: str, user_prompt: str) -> str:
    """Remote formalization call (OpenAI).

    Intentionally isolated for tests/mocking.
    """
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(f"openai package unavailable: {type(e).__name__}: {e}")

    model = (os.environ.get(_DEFAULT_MODEL_ENV) or "gpt-4o-mini").strip()
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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

    msg = resp.choices[0].message
    content = msg.content if hasattr(msg, "content") else None
    if not isinstance(content, str):
        raise RuntimeError("OpenAI response missing message content")
    return content


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


def formalize_journal_to_journal_json(run_dir: Path, template_id: str, retention: str) -> Dict[str, Any]:
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

    session_id, run_id, segs, transcript_version_id = _load_transcript_segments(run_dir)
    valid_seg_ids = _segment_id_set(segs)

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

    system_template = load_system_template_text("journal", tv.template_id).strip()

    seg_compact = [
        {
            "segment_id": int(s.get("segment_id", i)),
            "speaker": str(s.get("speaker") or "SPEAKER_00"),
            "text": str(s.get("text") or "").strip(),
        }
        for i, s in enumerate(segs)
        if str(s.get("text") or "").strip()
    ]

    user_prompt = f"""You are generating Stuart journal formalizations.
Return ONLY valid JSON for the journal.json v1 schema.

Rules (truth discipline):
- Do not invent events, actions, commitments, names, dates, places, or amounts.
- If something is unclear, mark it explicitly as uncertain or omit it.
- Narrative prose may be subjective and MAY omit citations.
- Any factual claim (events, plans, commitments, concrete actions, names, places, dates, amounts) MUST be supported by citations.
- key_points and action_items (if any) MUST be evidence-backed with non-empty citations.
- Citations are JSON objects: {{ "segment_id": <int> }} referencing REAL segment_id values from the transcript.
- action_items.assignee must be a speaker label like SPEAKER_00, otherwise null.
- Include ALL top-level keys (narrative_sections, key_points, action_items, feelings, mood) even if empty.

retention={retention}
template_id={tv.template_id}

Transcript segments (JSON array):
{json.dumps(seg_compact, indent=2, sort_keys=True)}
"""

    system_prompt = (
        "STUART FORMALIZER (journal.json v1)\n"
        "You must follow the system template instructions, but output MUST be JSON only.\n\n"
        + system_template
    )

    try:
        raw = _call_openai_journal_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception as e:
        # Remote unavailable: fall back, but record warning in header.
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
        validate_journal_v1(payload)
        _assert_citations_reference_real_segments(payload, valid_seg_ids)
        dump_json(out_path, payload, write_once=True)
        return {
            "kind": "journal_json",
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
        raw_path = artifacts / "journal_llm_raw.txt"
        _write_text_write_once(raw_path, raw)
        fail = _write_failure_receipt(run_dir, stage="journal_llm", error="non_json_output", detail={"raw_path": str(raw_path)})
        raise ValueError(f"LLM returned non-JSON journal output; see {raw_path} and {fail}")

    if not isinstance(llm_payload, dict):
        raw_path = artifacts / "journal_llm_raw.txt"
        _write_text_write_once(raw_path, raw)
        fail = _write_failure_receipt(run_dir, stage="journal_llm", error="json_not_object", detail={"raw_path": str(raw_path)})
        raise ValueError(f"LLM returned JSON but not an object; see {raw_path} and {fail}")

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
    return {
        "kind": "journal_json",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "created_ts": time.time(),
        "engine": "openai",
        "model": (os.environ.get(_DEFAULT_MODEL_ENV) or "gpt-4o-mini").strip(),
    }
