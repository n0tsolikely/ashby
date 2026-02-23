from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.store import sha256_file


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _overlap_ms(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    lo = max(a_start, b_start)
    hi = min(a_end, b_end)
    return max(0, hi - lo)


_WORD_RE = re.compile(r"\S+\s*")
_SPLIT_MIN_WORDS = 6
_SPLIT_DOMINANCE_THRESHOLD = 0.82
_MERGE_GAP_MS = 700


def _split_text_by_weights(text: str, weights: List[int]) -> List[str]:
    chunks = [m.group(0) for m in _WORD_RE.finditer(text or "")]
    n = len(chunks)
    if n == 0:
        return ["" for _ in weights]
    if len(weights) <= 1:
        return [text.strip()]
    total_w = sum(max(0, int(w)) for w in weights)
    if total_w <= 0:
        total_w = len(weights)
        weights = [1 for _ in weights]

    raw = [(max(0, int(w)) / total_w) * n for w in weights]
    counts = [int(x) for x in raw]
    remain = n - sum(counts)
    frac_idx = sorted(
        [(raw[i] - counts[i], i) for i in range(len(weights))],
        key=lambda t: (-t[0], t[1]),
    )
    for _, i in frac_idx:
        if remain <= 0:
            break
        counts[i] += 1
        remain -= 1

    # Ensure non-empty allocation where possible.
    for i in range(len(counts)):
        if n >= len(counts) and counts[i] <= 0:
            donor = max(range(len(counts)), key=lambda j: counts[j])
            if counts[donor] > 1:
                counts[donor] -= 1
                counts[i] += 1

    out: List[str] = []
    p = 0
    for c in counts:
        q = min(n, p + max(0, c))
        piece = "".join(chunks[p:q]).strip()
        out.append(piece)
        p = q
    if p < n and out:
        tail = "".join(chunks[p:]).strip()
        out[-1] = f"{out[-1]} {tail}".strip() if out[-1] else tail
    return out


def _merge_adjacent_same_speaker(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not segments:
        return []
    merged: List[Dict[str, Any]] = []
    for seg in segments:
        if not merged:
            merged.append(dict(seg))
            continue
        prev = merged[-1]
        same_speaker = prev.get("speaker") == seg.get("speaker")
        prev_end = int(prev.get("end_ms", 0) or 0)
        cur_start = int(seg.get("start_ms", 0) or 0)
        close_gap = (cur_start - prev_end) <= _MERGE_GAP_MS
        if same_speaker and close_gap:
            prev_text = str(prev.get("text") or "").strip()
            cur_text = str(seg.get("text") or "").strip()
            if prev_text and cur_text:
                prev["text"] = f"{prev_text} {cur_text}"
            elif cur_text:
                prev["text"] = cur_text
            prev["end_ms"] = max(prev_end, int(seg.get("end_ms", 0) or 0))
            prev["speaker_source"] = "diarization" if (
                prev.get("speaker_source") == "diarization" or seg.get("speaker_source") == "diarization"
            ) else prev.get("speaker_source", "transcript")
            continue
        merged.append(dict(seg))

    for i, seg in enumerate(merged):
        seg["segment_id"] = i
    return merged


def _align_one_segment(seg: Dict[str, Any], d_segs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        start_ms = int(seg.get("start_ms", 0) or 0)
        end_ms = int(seg.get("end_ms", 0) or 0)
    except Exception:
        start_ms, end_ms = 0, 0

    text = str(seg.get("text") or "").strip()
    base_speaker = seg.get("speaker") if isinstance(seg.get("speaker"), str) and seg.get("speaker") else "SPEAKER_00"

    # Fall back to transcript speaker when timing is unusable.
    if end_ms <= start_ms or not d_segs:
        out = dict(seg)
        out["speaker"] = base_speaker
        out["speaker_source"] = "transcript"
        return [out]

    overlaps: List[Dict[str, Any]] = []
    for d in d_segs:
        try:
            ds = int(d.get("start_ms", 0) or 0)
            de = int(d.get("end_ms", 0) or 0)
        except Exception:
            continue
        ov = _overlap_ms(start_ms, end_ms, ds, de)
        if ov <= 0:
            continue
        sp = d.get("speaker") if isinstance(d.get("speaker"), str) and d.get("speaker") else None
        if not sp:
            continue
        overlaps.append(
            {
                "speaker": sp,
                "ov_ms": ov,
                "span_start": max(start_ms, ds),
                "span_end": min(end_ms, de),
            }
        )

    if not overlaps:
        out = dict(seg)
        out["speaker"] = base_speaker
        out["speaker_source"] = "transcript"
        return [out]

    # Speaker totals within this ASR segment.
    totals: Dict[str, int] = {}
    for o in overlaps:
        totals[o["speaker"]] = totals.get(o["speaker"], 0) + int(o["ov_ms"])
    best_sp = max(totals.keys(), key=lambda s: totals[s])

    # If one speaker dominates or text is short, assign whole segment.
    total_ov = sum(totals.values())
    dominance = (totals.get(best_sp, 0) / float(total_ov)) if total_ov > 0 else 1.0
    word_count = len(_WORD_RE.findall(text))
    if len(totals) == 1 or word_count < _SPLIT_MIN_WORDS or dominance >= _SPLIT_DOMINANCE_THRESHOLD:
        out = dict(seg)
        out["speaker"] = best_sp
        out["speaker_source"] = "diarization"
        return [out]

    # Build ordered spans; merge adjacent same-speaker micro-spans.
    spans = sorted(overlaps, key=lambda x: (x["span_start"], x["span_end"]))
    compact: List[Dict[str, Any]] = []
    for sp in spans:
        if (
            compact
            and compact[-1]["speaker"] == sp["speaker"]
            and int(sp["span_start"]) - int(compact[-1]["span_end"]) <= _MERGE_GAP_MS
        ):
            compact[-1]["span_end"] = max(int(compact[-1]["span_end"]), int(sp["span_end"]))
            compact[-1]["ov_ms"] = int(compact[-1]["ov_ms"]) + int(sp["ov_ms"])
        else:
            compact.append(dict(sp))

    pieces = _split_text_by_weights(text, [int(s["ov_ms"]) for s in compact])
    out_list: List[Dict[str, Any]] = []
    for idx, sp in enumerate(compact):
        piece = pieces[idx].strip() if idx < len(pieces) else ""
        if not piece:
            continue
        out = dict(seg)
        out["start_ms"] = int(sp["span_start"])
        out["end_ms"] = int(sp["span_end"])
        out["speaker"] = str(sp["speaker"])
        out["speaker_source"] = "diarization"
        out["text"] = piece
        out["source_segment_id"] = seg.get("segment_id")
        out_list.append(out)

    if out_list:
        return out_list
    # Defensive fallback.
    out = dict(seg)
    out["speaker"] = best_sp
    out["speaker_source"] = "diarization"
    return [out]


def align_transcript_time_overlap(run_dir: Path) -> Dict[str, Any]:
    """Stage 3 alignment: diarization ↔ ASR.

    Reads (write-once inputs produced earlier):
      - run_dir/artifacts/transcript.json (v1)
      - run_dir/artifacts/diarization.json (v1) (optional)

    Writes (write-once):
      - run_dir/artifacts/aligned_transcript.json (v1)

    Truth:
      - If diarization file missing, we still write aligned output by copying transcript speakers.
    """
    artifacts_dir = run_dir / "artifacts"
    tpath = artifacts_dir / "transcript.json"
    if not tpath.exists():
        raise FileNotFoundError(f"transcript.json missing: {tpath}")

    dpath = artifacts_dir / "diarization.json"
    legacy_dpath = artifacts_dir / "diarization_segments.json"

    out_path = artifacts_dir / "aligned_transcript.json"
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite aligned transcript: {out_path}")

    t = _load_json(tpath)
    src_dpath = dpath if dpath.exists() else (legacy_dpath if legacy_dpath.exists() else None)
    diar = _load_json(src_dpath) if src_dpath is not None else {"segments": [], "engine": "missing"}

    t_segs = t.get("segments") or []
    d_segs = diar.get("segments") or []

    aligned: List[Dict[str, Any]] = []
    for seg in t_segs:
        if not isinstance(seg, dict):
            continue
        aligned.extend(_align_one_segment(seg, d_segs))
    aligned = _merge_adjacent_same_speaker(aligned)

    payload: Dict[str, Any] = {
        "version": 1,
        "session_id": t.get("session_id", ""),
        "run_id": t.get("run_id", ""),
        "segments": aligned,
        "engine": "time_overlap_v1",
        "asr_engine": t.get("engine", ""),
        "diarization_engine": diar.get("engine", "missing"),
        "diarization_present": bool(src_dpath is not None),
        "diarization_source": (src_dpath.name if src_dpath is not None else "missing"),
    }

    dump_json(out_path, payload, write_once=True)

    return {
        "kind": "aligned_transcript",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "created_ts": time.time(),
        "engine": payload["engine"],
    }
