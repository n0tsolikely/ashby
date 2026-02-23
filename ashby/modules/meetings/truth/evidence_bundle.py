from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from ashby.core.results import ArtifactResult, ok_artifact
from ashby.core.truth.evidence import Citation, EvidenceBundle

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.session_state import load_session_state


@dataclass(frozen=True)
class TranscriptEvidence:
    kind: Literal["aligned_transcript", "transcript"]
    path: Path
    rel_path: str
    engine: str
    segments: List[Dict[str, Any]]


def _rel_path_under_root(path: Path) -> str:
    """Return a storage-safe relative path under STUART_ROOT.

    We intentionally keep truth spine paths relative so artifacts can be moved
    with the runtime root without breaking references.
    """
    lay = init_stuart_root()
    root = lay.root.resolve()
    p = path.resolve()
    try:
        rel = p.relative_to(root)
    except Exception as e:
        raise ValueError(f"path not under STUART_ROOT: {p} (root={root})") from e
    return rel.as_posix()


def _load_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def load_transcript_evidence(run_dir: Path) -> TranscriptEvidence:
    """Load transcript evidence for a run.

    Preference order:
      1) aligned_transcript.json (meeting mode)
      2) transcript.json

    Both are treated as acceptable evidence substrates.
    """
    artifacts = run_dir / "artifacts"

    aligned = artifacts / "aligned_transcript.json"
    raw = artifacts / "transcript.json"

    if aligned.exists():
        # Deterministic fallback rail:
        # when transcript.json is stub-engine, keep truth validation on transcript.json
        # so segment anchors match deterministic formalization outputs.
        if raw.exists():
            try:
                raw_payload = _load_json(raw)
                if str(raw_payload.get("engine") or "").strip().lower() == "stub":
                    segs = list(raw_payload.get("segments") or [])
                    return TranscriptEvidence(
                        kind="transcript",
                        path=raw,
                        rel_path=_rel_path_under_root(raw),
                        engine=str(raw_payload.get("engine") or ""),
                        segments=[s for s in segs if isinstance(s, dict)],
                    )
            except Exception:
                pass

        payload = _load_json(aligned)
        segs = list(payload.get("segments") or [])
        return TranscriptEvidence(
            kind="aligned_transcript",
            path=aligned,
            rel_path=_rel_path_under_root(aligned),
            engine=str(payload.get("engine") or ""),
            segments=[s for s in segs if isinstance(s, dict)],
        )

    if raw.exists():
        payload = _load_json(raw)
        segs = list(payload.get("segments") or [])
        return TranscriptEvidence(
            kind="transcript",
            path=raw,
            rel_path=_rel_path_under_root(raw),
            engine=str(payload.get("engine") or ""),
            segments=[s for s in segs if isinstance(s, dict)],
        )

    raise FileNotFoundError(
        f"Missing transcript evidence (need aligned_transcript.json or transcript.json): {artifacts}"
    )


def _coerce_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def build_transcript_citations(*, session_id: str, transcript: TranscriptEvidence) -> List[Citation]:
    """Represent the transcript as a set of addressable citations.

    IMPORTANT: this returns citations for *all* segments, not just the ones
    referenced by a particular draft.

    That makes policy validation possible without reading from disk.
    """
    out: List[Citation] = []
    for seg in transcript.segments:
        sid_i = _coerce_int(seg.get("segment_id"))
        if sid_i is None or sid_i < 0:
            continue

        start_ms = _coerce_int(seg.get("start_ms"))
        end_ms = _coerce_int(seg.get("end_ms"))
        if start_ms is not None and end_ms is not None and start_ms > end_ms:
            start_ms, end_ms = None, None

        speaker_id = seg.get("speaker") if isinstance(seg.get("speaker"), str) else None

        out.append(
            Citation(
                session_id=session_id,
                artifact_path=transcript.rel_path,
                segment_id=str(sid_i),
                start_ms=start_ms,
                end_ms=end_ms,
                speaker_id=speaker_id,
            )
        )

    return out


def _load_active_speaker_overlay(*, session_id: str) -> Tuple[Optional[str], Optional[Path], Dict[str, str]]:
    st = load_session_state(session_id)
    ovr_id = st.get("active_speaker_overlay_id")
    if not isinstance(ovr_id, str) or not ovr_id.strip():
        return None, None, {}

    lay = init_stuart_root()
    overlay_path = lay.overlays / session_id / "speaker_map" / f"{ovr_id}.json"
    if not overlay_path.exists():
        return ovr_id, overlay_path, {}

    data = _load_json(overlay_path)
    mapping_raw = data.get("mapping")
    mapping: Dict[str, str] = {}
    if isinstance(mapping_raw, dict):
        for k, v in mapping_raw.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                mapping[k.strip().upper()] = v.strip()

    return ovr_id, overlay_path, mapping


def build_meetings_evidence_bundle(
    *,
    session_id: str,
    run_id: str,
    run_dir: Path,
    mode: str,
) -> EvidenceBundle:
    """Build an EvidenceBundle for the Meetings module.

    Meetings evidence is currently:
    - transcript segments (as citations)
    - optional diarization metadata
    - optional active speaker-map overlay mapping

    No external calls. Deterministic given artifacts.
    """
    transcript = load_transcript_evidence(run_dir)
    citations = build_transcript_citations(session_id=session_id, transcript=transcript)

    # Artifact results: transcript + optional diarization + optional speaker overlay.
    artifacts: List[ArtifactResult] = []

    artifacts.append(
        ok_artifact(
            artifact_type="meetings_transcript_v1",
            artifacts={"transcript_json": transcript.rel_path},
            metadata={
                "run_id": run_id,
                "mode": mode,
                "kind": transcript.kind,
                "engine": transcript.engine,
                "segment_count": len(citations),
            },
        )
    )

    diar_path = run_dir / "artifacts" / "diarization.json"
    if diar_path.exists():
        diar = _load_json(diar_path)
        confidence = diar.get("confidence")
        try:
            conf_f = float(confidence) if confidence is not None else None
        except Exception:
            conf_f = None

        artifacts.append(
            ok_artifact(
                artifact_type="meetings_diarization_v1",
                artifacts={"diarization_json": _rel_path_under_root(diar_path)},
                metadata={
                    "run_id": run_id,
                    "mode": mode,
                    "confidence": conf_f,
                    "confidence_source": diar.get("confidence_source"),
                    "note": diar.get("note"),
                },
            )
        )

    ovr_id, ovr_path, mapping = _load_active_speaker_overlay(session_id=session_id)
    if ovr_id is not None:
        artifacts.append(
            ok_artifact(
                artifact_type="meetings_speaker_map_overlay_v1",
                artifacts={
                    "speaker_map_overlay_json": (
                        _rel_path_under_root(ovr_path) if ovr_path is not None else "(missing)"
                    )
                },
                metadata={
                    "session_id": session_id,
                    "overlay_id": ovr_id,
                    "mapping": mapping,
                    "mapping_count": len(mapping),
                },
            )
        )

    # Keep notes minimal (human debugging only).
    notes = [
        f"meetings.mode={mode}",
        f"meetings.run_id={run_id}",
    ]

    return EvidenceBundle(
        citations=citations,
        action_results=[],
        artifact_results=artifacts,
        notes=notes,
        errors=[],
    )
