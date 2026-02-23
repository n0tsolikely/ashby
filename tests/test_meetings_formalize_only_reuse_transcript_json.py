from __future__ import annotations

import json
from pathlib import Path

from ashby.core.profile import ExecutionProfile
from ashby.modules.meetings.adapters.adapter_matrix import MeetingsAdapterMatrix, get_meetings_adapter_matrix
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.pipeline import job_runner
from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.store import add_contribution, create_run, create_session


def test_formalize_only_rerun_reuses_transcript_json_and_skips_heavy_stages(tmp_path: Path, monkeypatch) -> None:
    """QUEST_070 regression:

    A formalize-only rerun (reuse_run_id) must:
      - NOT call normalize/transcribe/diarize/align
      - copy transcript.json/aligned_transcript.json into the new run
      - produce new derived outputs (minutes.*) with the *new* run_id
    """

    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    session_id = create_session(mode="meeting", title="t")

    # Contribution exists only so input resolution can succeed. Content doesn't matter because
    # reuse_run_id should skip all audio-derived stages.
    src = tmp_path / "src.bin"
    src.write_bytes(b"dummy")
    add_contribution(session_id=session_id, source_path=src, source_kind="audio")

    # Create a source run_id with transcript substrates (we do NOT execute it).
    source_run_id = create_run(session_id=session_id, plan={"steps": []})
    lay = init_stuart_root()
    src_run_dir = lay.runs / source_run_id
    artifacts = src_run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    transcript_payload = {
        "version": 1,
        "session_id": session_id,
        "run_id": source_run_id,
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "Hello."},
            {"segment_id": 1, "start_ms": 1000, "end_ms": 2000, "speaker": "SPEAKER_01", "text": "World."},
        ],
        "engine": "test",
    }
    (artifacts / "transcript.json").write_text(json.dumps(transcript_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (artifacts / "aligned_transcript.json").write_text(json.dumps(transcript_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Create a new run that reuses the prior run's transcript substrate.
    rerun_id = create_run(
        session_id=session_id,
        plan={
            "steps": [
                {"kind": "formalize", "params": {"mode": "meeting", "template": "default", "reuse_run_id": source_run_id}}
            ]
        },
    )

    # Adapter matrix for the rerun: pdf is allowed; all heavy stages must not be called.
    real = get_meetings_adapter_matrix(ExecutionProfile.LOCAL_ONLY)

    def boom(*_a, **_kw):
        raise RuntimeError("heavy stage should not be called when reuse_run_id is set")

    fake = MeetingsAdapterMatrix(
        profile=real.profile,
        normalize=boom,
        align=boom,
        transcribe=boom,
        diarize=boom,
        pdf=real.pdf,
    )
    monkeypatch.setattr(job_runner, "get_meetings_adapter_matrix", lambda _profile: fake)

    res = run_job(rerun_id)
    assert res.ok is True

    rerun_dir = lay.runs / rerun_id

    # Transcript substrate must be present in the rerun.
    assert (rerun_dir / "artifacts" / "transcript.json").exists()
    assert (rerun_dir / "artifacts" / "aligned_transcript.json").exists()

    # Derived outputs must reflect the NEW run_id (not the reused source run_id).
    minutes_path = rerun_dir / "artifacts" / "minutes.json"
    assert minutes_path.exists()
    minutes_payload = json.loads(minutes_path.read_text(encoding="utf-8"))
    assert minutes_payload.get("run_id") == rerun_id

    # Audit receipt must exist.
    reuse_receipt = rerun_dir / "inputs" / "reused_transcript.json"
    assert reuse_receipt.exists()
    receipt_payload = json.loads(reuse_receipt.read_text(encoding="utf-8"))
    assert receipt_payload.get("reuse_run_id") == source_run_id
