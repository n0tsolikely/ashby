from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class PrimaryOutputPointer:
    kind: str
    path: str
    sha256: str
    created_ts: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "created_ts": self.created_ts,
        }


def _first_artifact(artifacts: List[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    for a in artifacts:
        if not isinstance(a, dict):
            continue
        if a.get("kind") == kind:
            return a
    return None


def _last_artifact(artifacts: List[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    for a in reversed(artifacts):
        if not isinstance(a, dict):
            continue
        if a.get("kind") == kind:
            return a
    return None


def _infer_mode_from_artifacts(artifacts: List[Dict[str, Any]]) -> Optional[str]:
    kinds = {a.get("kind") for a in artifacts if isinstance(a, dict)}
    if "minutes_json" in kinds or "minutes_md" in kinds or "minutes_pdf" in kinds or "minutes_txt" in kinds:
        return "meeting"
    if "journal_json" in kinds or "journal_md" in kinds or "journal_pdf" in kinds or "journal_txt" in kinds:
        return "journal"
    return None


def build_primary_outputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build mode-aware primary outputs from a run state.

    This is deterministic and *does not* touch the filesystem or mutate the run.
    """
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), list) else []
    artifacts = [a for a in artifacts if isinstance(a, dict)]

    mode = _infer_mode_from_artifacts(artifacts)
    if mode is None:
        plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        for st in steps:
            if not isinstance(st, dict):
                continue
            kind = str(st.get("kind") or "").strip().lower()
            if kind not in {"formalize", "transcribe"}:
                continue
            params = st.get("params") if isinstance(st.get("params"), dict) else {}
            m = str(params.get("mode") or "").strip().lower()
            if m in {"meeting", "journal"}:
                mode = m
                break

    # Required outputs for a formalize run (when present)
    # Note: evidence_map is mode-agnostic.
    minutes_json = _first_artifact(artifacts, "minutes_json")
    minutes_md = _first_artifact(artifacts, "minutes_md")
    minutes_pdf = _first_artifact(artifacts, "minutes_pdf")
    minutes_txt = _first_artifact(artifacts, "minutes_txt")

    journal_json = _first_artifact(artifacts, "journal_json")
    journal_md = _first_artifact(artifacts, "journal_md")
    journal_pdf = _first_artifact(artifacts, "journal_pdf")
    journal_txt = _first_artifact(artifacts, "journal_txt")

    ev = _first_artifact(artifacts, "evidence_map")
    transcript = _first_artifact(artifacts, "transcript")
    aligned_transcript = _first_artifact(artifacts, "aligned_transcript")
    produced_tv = _last_artifact(artifacts, "produced_transcript_version")
    consumed_tv = _last_artifact(artifacts, "consumed_transcript_version")

    def ptr(a: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not a:
            return None
        # Only include fields we trust/need
        if not all(k in a for k in ("kind", "path", "sha256", "created_ts")):
            return None
        return {
            "kind": a["kind"],
            "path": a["path"],
            "sha256": a["sha256"],
            "created_ts": a["created_ts"],
        }

    out: Dict[str, Any] = {
        "mode": mode,
        "json": ptr(minutes_json if mode == "meeting" else journal_json if mode == "journal" else None),
        "md": ptr(minutes_md if mode == "meeting" else journal_md if mode == "journal" else None),
        "pdf": ptr(minutes_pdf if mode == "meeting" else journal_pdf if mode == "journal" else None),
        "txt": ptr(minutes_txt if mode == "meeting" else journal_txt if mode == "journal" else None),
        "evidence_map": ptr(ev),
        "transcript": ptr(aligned_transcript) or ptr(transcript),
    }
    if isinstance(produced_tv, dict):
        trv = produced_tv.get("transcript_version_id")
        if isinstance(trv, str) and trv:
            out["produced_transcript_version_id"] = trv
    if isinstance(consumed_tv, dict):
        trv = consumed_tv.get("transcript_version_id")
        if isinstance(trv, str) and trv:
            out["consumed_transcript_version_id"] = trv
    return out


def resolve_primary_outputs(run_id: str) -> Dict[str, Any]:
    """Resolve primary outputs for a run_id.

    Rule:
    - Prefer run.json['primary_outputs'] if present.
    - Otherwise, derive from artifacts and return the derived structure.
      (We don't auto-write back here; job_runner should populate at end-of-run.)
    """
    from ashby.modules.meetings.store import get_run_state

    state = get_run_state(run_id)
    po = state.get("primary_outputs")
    if isinstance(po, dict) and po:
        return po
    return build_primary_outputs(state)
