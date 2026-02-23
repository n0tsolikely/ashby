from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List

from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.store import sha256_file
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub


def _fw_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _fw_enabled() -> bool:
    """Gate real ASR behind explicit opt-in for deterministic test/runtime behavior."""
    raw = (os.environ.get("ASHBY_ASR_ENABLE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def transcribe_faster_whisper_or_stub(run_dir: Path) -> Dict[str, Any]:
    """LOCAL_ONLY ASR adapter.

    Reads:
      run_dir/artifacts/normalized.wav

    Writes (write-once):
      run_dir/artifacts/transcript.txt
      run_dir/artifacts/transcript.json  (version=1)

    Truth:
      - If faster-whisper unavailable, we fall back to stub transcript but mark engine='stub' + warning.
    """
    in_path = run_dir / "artifacts" / "normalized.wav"
    if not in_path.exists():
        raise FileNotFoundError(f"normalized.wav missing: {in_path}")

    txt_path = run_dir / "artifacts" / "transcript.txt"
    json_path = run_dir / "artifacts" / "transcript.json"
    if txt_path.exists() or json_path.exists():
        raise FileExistsError("Refusing to overwrite transcript artifacts (write-once)")

    session_id = run_dir.parent.parent.name if run_dir.parent.name == "runs" else ""
    run_id = run_dir.name

    segments: List[Dict[str, Any]] = []
    warning = ""

    if _fw_available() and _fw_enabled():
        try:
            from faster_whisper import WhisperModel

            model_name = (os.environ.get("ASHBY_ASR_MODEL") or "small").strip()
            device = (os.environ.get("ASHBY_ASR_DEVICE") or "cpu").strip()
            compute_type = (os.environ.get("ASHBY_ASR_COMPUTE_TYPE") or "int8").strip()

            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            fw_segments, _info = model.transcribe(str(in_path), beam_size=5)

            lines: List[str] = []
            for i, seg in enumerate(fw_segments):
                start_ms = int(seg.start * 1000)
                end_ms = int(seg.end * 1000)
                text = (seg.text or "").strip()
                segments.append(
                    {
                        "segment_id": i,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "speaker": "SPEAKER_00",
                        "text": text,
                    }
                )
                lines.append(f"[{start_ms}-{end_ms}] SPEAKER_00: {text}")

            txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            payload: Dict[str, Any] = {
                "version": 1,
                "session_id": session_id,
                "run_id": run_id,
                "segments": segments,
                "engine": "faster-whisper",
                "model": model_name,
            }
            dump_json(json_path, payload, write_once=True)

            return {
                "kind": "transcript",
                "path": str(txt_path),
                "sha256": sha256_file(txt_path),
                "created_ts": time.time(),
                "engine": "faster-whisper",
                "json_path": str(json_path),
            }
        except Exception as e:
            warning = f"faster-whisper failed: {type(e).__name__}: {e}"

    if not warning:
        if _fw_available() and not _fw_enabled():
            warning = "faster-whisper available but disabled; using stub transcript."
        else:
            warning = "faster-whisper not installed; using stub transcript."

    # QUEST_057: the stub transcriber now emits both transcript.txt AND transcript.json.
    # This keeps downstream indexing + formalize on the JSON substrate (no brittle .txt parsing).
    art = transcribe_stub(run_dir)

    # Safety rail: if a legacy stub produced only transcript.txt, emit a minimal JSON payload.
    if not json_path.exists():
        raw = Path(art["path"]).read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(raw):
            segments.append(
                {
                    "segment_id": i,
                    "start_ms": 0,
                    "end_ms": 0,
                    "speaker": "SPEAKER_00",
                    "text": line.strip(),
                }
            )
        payload = {
            "version": 1,
            "session_id": session_id,
            "run_id": run_id,
            "segments": segments,
            "engine": "stub",
            "warning": warning,
        }
        dump_json(json_path, payload, write_once=True)

    return {
        "kind": "transcript",
        "path": str(Path(art["path"])),
        "sha256": sha256_file(Path(art["path"])),
        "created_ts": time.time(),
        "engine": "stub",
        "json_path": str(json_path),
    }
