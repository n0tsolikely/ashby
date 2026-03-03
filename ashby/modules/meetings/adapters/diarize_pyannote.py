from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.store import sha256_file


def _pyannote_available() -> bool:
    try:
        import pyannote.audio  # noqa: F401
        return True
    except Exception:
        return False


def diarize_pyannote(run_dir: Path) -> Dict[str, Any]:
    """Diarization adapter (LOCAL_ONLY).

    Contract:
    - Reads normalized input from: run_dir/artifacts/normalized.wav (produced by QUEST_034)
    - Writes: run_dir/artifacts/diarization.json (write-once, version=1)
    - Returns artifact dict for run_state.

    Truth rule:
    - If pyannote is unavailable or HF token missing, we do NOT claim diarization succeeded.
      We write a stub payload with explicit 'engine' and 'warning' fields.
    """
    in_path = run_dir / "artifacts" / "normalized.wav"
    if not in_path.exists():
        raise FileNotFoundError(f"normalized.wav missing: {in_path}")

    out_path = run_dir / "artifacts" / "diarization.json"
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite diarization artifact: {out_path}")

    session_id = run_dir.parent.parent.name if run_dir.parent.name == "runs" else ""
    run_id = run_dir.name

    # Optional speaker hint (written by job_runner): inputs/speaker_hint.json
    speaker_hint = None
    hint_path = run_dir / "inputs" / "speaker_hint.json"
    if hint_path.exists():
        try:
            data = json.loads(hint_path.read_text(encoding="utf-8"))
            v = data.get("speakers")
            speaker_hint = int(v) if v is not None else None
        except Exception:
            speaker_hint = None

    hf_token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
    can_pyannote = _pyannote_available() and bool(hf_token)

    segments: List[Dict[str, Any]] = []
    payload: Dict[str, Any] = {
        "version": 1,
        "session_id": session_id,
        "run_id": run_id,
        "segments": segments,
        # Confidence:
        # - We require confidence fields for the Codex contract.
        # - pyannote speaker diarization does not expose a stable per-segment confidence score, so
        #   we use a deterministic default and record the source explicitly.
        "confidence": 0.0,
        "confidence_source": "stub",
    }


    if speaker_hint is not None:
        payload["speaker_hint"] = speaker_hint

    if can_pyannote:
        try:
            # PyTorch >=2.6 defaults torch.load(weights_only=True), but current
            # pyannote checkpoints still require full-object unpickling.
            os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
            from pyannote.audio import Pipeline
            # pyannote.audio API drift handling:
            # - older versions: use_auth_token=
            # - newer versions: token=
            auth_arg = "token"
            try:
                pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=hf_token)
            except TypeError:
                auth_arg = "use_auth_token"
                pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf_token)
            payload["pyannote_auth_arg"] = auth_arg
            if speaker_hint is not None and speaker_hint >= 2:
                try:
                    diar = pipe(str(in_path), num_speakers=speaker_hint)
                except TypeError:
                    diar = pipe(str(in_path), min_speakers=speaker_hint, max_speakers=speaker_hint)
            else:
                diar = pipe(str(in_path))
            for turn, track, speaker in diar.itertracks(yield_label=True):
                # pyannote returns (segment, track, label). Some API variants or
                # wrappers may swap the first two fields; normalize defensively.
                if not hasattr(turn, "start") and hasattr(track, "start"):
                    turn, track = track, turn
                segments.append({
                    "segment_id": len(segments),
                    "start_ms": int(turn.start * 1000),
                    "end_ms": int(turn.end * 1000),
                    "speaker": str(speaker),
                    "confidence": 1.0,
                })
            payload["engine"] = "pyannote"
            # Deterministic confidence default (pyannote does not provide a stable score)
            payload["confidence"] = 1.0 if segments else 0.0
            payload["confidence_source"] = "default_1.0"
        except Exception as e:
            payload["engine"] = "stub"
            payload["warning"] = f"pyannote failed at runtime: {type(e).__name__}: {e}"
    else:
        payload["engine"] = "stub"
        if not _pyannote_available():
            payload["warning"] = "pyannote not installed; diarization unavailable (stub output)."
        elif not hf_token:
            payload["warning"] = "HF_TOKEN missing; diarization model gated/unavailable (stub output)."

    dump_json(out_path, payload, write_once=True)

    return {
        "kind": "diarization",
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "created_ts": time.time(),
        "engine": payload.get("engine", "stub"),
    }


# Backward-compatible alias (if any code/tests imported a different name)
def diarize_pyannote_or_stub(run_dir: Path) -> Dict[str, Any]:
    return diarize_pyannote(run_dir)
