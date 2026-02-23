from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, TypedDict


# ----------------------------
# Canonical JSON Artifact Schemas — v1
# ----------------------------

# Transcript segment (v1)
class TranscriptSegmentV1(TypedDict, total=False):
    segment_id: int
    start_ms: int
    end_ms: int
    speaker: str
    text: str


class TranscriptV1(TypedDict):
    version: int
    session_id: str
    run_id: str
    segments: List[TranscriptSegmentV1]


# Transcript version segment (v1)
class TranscriptVersionSegmentV1(TypedDict, total=False):
    segment_id: int
    start_ms: int
    end_ms: int
    speaker: str
    text: str
    confidence: float


class TranscriptVersionV1(TypedDict):
    version: int
    transcript_version_id: str
    session_id: str
    run_id: str
    created_ts: float
    diarization_enabled: bool
    asr_engine: str
    audio_ref: Dict[str, Any]
    segments: List[TranscriptVersionSegmentV1]


# Diarization segment (v1)
class DiarizationSegmentV1(TypedDict, total=False):
    segment_id: int
    start_ms: int
    end_ms: int
    speaker: str
    confidence: float


class DiarizationSegmentsV1(TypedDict):
    version: int
    session_id: str
    run_id: str
    segments: List[DiarizationSegmentV1]


# Aligned transcript (v1) — diarization merged onto ASR segments
class AlignedTranscriptSegmentV1(TranscriptSegmentV1, total=False):
    # alignment-specific fields may be added in later versions
    pass


class AlignedTranscriptV1(TypedDict):
    version: int
    session_id: str
    run_id: str
    segments: List[AlignedTranscriptSegmentV1]


# Evidence map (already v1 in current code; schema noted here)
class EvidenceClaimV1(TypedDict, total=False):
    claim_id: str
    text: str
    citations: List[Dict[str, Any]]


class EvidenceMapV1(TypedDict):
    version: int
    session_id: str
    run_id: str
    claims: List[EvidenceClaimV1]


# Search results (v1)
class SearchResultItemV1(TypedDict, total=False):
    snippet: str
    citation: Dict[str, Any]


class SearchResultsV1(TypedDict, total=False):
    version: int
    query: str
    total_hits: int
    message: str
    results: List[SearchResultItemV1]


def dump_json(path: Path, payload: Dict[str, Any], *, write_once: bool = False) -> None:
    """Deterministic JSON writer.

    - sort_keys=True, indent=2
    - write_once=True refuses overwrite (immutability rail)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if write_once and path.exists():
        raise FileExistsError(f"Refusing to overwrite JSON artifact: {path}")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_keys(payload: Dict[str, Any], keys: List[str]) -> None:
    for k in keys:
        if k not in payload:
            raise ValueError(f"Missing required key: {k}")


def validate_transcript_v1(payload: Dict[str, Any]) -> None:
    require_keys(payload, ["version", "session_id", "run_id", "segments"])
    if int(payload["version"]) != 1:
        raise ValueError("TranscriptV1 version must be 1")
    if not isinstance(payload["segments"], list):
        raise ValueError("TranscriptV1 segments must be a list")


def validate_transcript_version_v1(payload: Dict[str, Any]) -> None:
    require_keys(
        payload,
        [
            "version",
            "transcript_version_id",
            "session_id",
            "run_id",
            "created_ts",
            "diarization_enabled",
            "asr_engine",
            "audio_ref",
            "segments",
        ],
    )
    if int(payload["version"]) != 1:
        raise ValueError("TranscriptVersionV1 version must be 1")
    if not str(payload.get("transcript_version_id") or "").startswith("trv_"):
        raise ValueError("TranscriptVersionV1 transcript_version_id must start with trv_")
    if not isinstance(payload.get("segments"), list):
        raise ValueError("TranscriptVersionV1 segments must be a list")
    if not isinstance(payload.get("audio_ref"), dict):
        raise ValueError("TranscriptVersionV1 audio_ref must be an object")
    if not isinstance(payload.get("diarization_enabled"), bool):
        raise ValueError("TranscriptVersionV1 diarization_enabled must be a bool")

    try:
        float(payload.get("created_ts"))
    except Exception as exc:  # pragma: no cover - defensive cast guard
        raise ValueError("TranscriptVersionV1 created_ts must be numeric") from exc

    asr_engine = str(payload.get("asr_engine") or "").strip()
    if not asr_engine:
        raise ValueError("TranscriptVersionV1 asr_engine must be non-empty")

    for seg in payload["segments"]:
        if not isinstance(seg, dict):
            raise ValueError("TranscriptVersionV1 segment must be an object")
        for required in ("segment_id", "start_ms", "end_ms", "text"):
            if required not in seg:
                raise ValueError(f"TranscriptVersionV1 segment missing {required}")


def validate_diarization_v1(payload: Dict[str, Any]) -> None:
    require_keys(payload, ["version", "session_id", "run_id", "segments"])
    if int(payload["version"]) != 1:
        raise ValueError("DiarizationSegmentsV1 version must be 1")
    if not isinstance(payload["segments"], list):
        raise ValueError("DiarizationSegmentsV1 segments must be a list")

    # Truth rail (Codex): diarization must include confidence per segment when segments exist.
    for s in payload["segments"]:
        if not isinstance(s, dict):
            raise ValueError("DiarizationSegmentsV1 segment must be an object")
        if "confidence" not in s:
            raise ValueError("DiarizationSegmentsV1 segment missing confidence")
        try:
            float(s.get("confidence", 0.0))
        except Exception as exc:  # pragma: no cover - defensive cast guard
            raise ValueError("DiarizationSegmentsV1 segment confidence must be a float") from exc
