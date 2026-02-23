from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from ashby.modules.meetings.pipeline.job_runner import run_job
from ashby.modules.meetings.store import add_contribution, create_run, create_session


def _gen_wav(path: Path) -> None:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not installed")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def _normalize_md(text: str) -> str:
    """Strip run-specific metadata so golden assertions are deterministic."""
    # run_id and created_ts are dynamic
    text = re.sub(r"^\- run_id: `[^`]*`\s*$", "- run_id: `<RUN_ID>`", text, flags=re.MULTILINE)
    text = re.sub(r"^\- created_ts: `[^`]*`\s*$", "- created_ts: `<CREATED_TS>`", text, flags=re.MULTILINE)
    # session_id can be empty or dynamic depending on store impl
    text = re.sub(r"^\- session_id: `[^`]*`\s*$", "- session_id: `<SESSION_ID>`", text, flags=re.MULTILINE)
    return text.strip() + "\n"


MEETING_GOLDEN = _normalize_md(
    """# Meeting Minutes

## Metadata
- session_id: ``
- run_id: `run_x`
- template_id: `default`
- retention: `MED`
- created_ts: `0`
- diarization_confidence: `0.0`
- speaker_identity_note: diarization confidence is low; speaker attribution may be unreliable.

## Participants
- `SPEAKER_00`
- `SPEAKER_01`

## Topics
- (topic_001) **Transcript**: Deterministic fallback: transcript-backed notes (no invented decisions/actions). [S0@00:00:00–00:00:00] [S1@00:00:00–00:00:00] [S2@00:00:00–00:00:00] [S3@00:00:00–00:00:00]

## Decisions
No explicit decisions recorded.

## Action Items
No action items recorded.

## Notes
- (note_0000) SPEAKER_00: Hello, this is a sample speaker line. [S0@00:00:00–00:00:00]
- (note_0001) SPEAKER_01: And this is another speaker line. [S1@00:00:00–00:00:00]
- (note_0002) SPEAKER_01: I made kimchi yesterday and it was spicy. [S2@00:00:00–00:00:00]
- (note_0003) SPEAKER_00: Second line from speaker 00 for extraction tests. [S3@00:00:00–00:00:00]

## Open Questions
_No open questions._
"""
)


JOURNAL_GOLDEN = _normalize_md(
    """# Journal Entry

## Metadata
- session_id: ``
- run_id: `run_x`
- template_id: `default`
- retention: `MED`
- created_ts: `0`

## Narrative
### Transcript
SPEAKER_00: Hello, this is a sample speaker line.
SPEAKER_01: And this is another speaker line.
SPEAKER_01: I made kimchi yesterday and it was spicy.
SPEAKER_00: Second line from speaker 00 for extraction tests.
[S0@00:00:00–00:00:00] [S1@00:00:00–00:00:00] [S2@00:00:00–00:00:00] [S3@00:00:00–00:00:00]


## Key Points
_No key points._

## Feelings
_No feelings._

## Action Items
_No action items._
"""
)


def test_e2e_meeting_outputs_exist_and_match_golden(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(session_id=ses, plan={"steps": [{"name": "formalize", "params": {"mode": "meeting"}}]})
    res = run_job(run_id)
    assert res.ok is True and res.status == "succeeded"

    run_dir = root / "runs" / run_id
    # Required artifacts
    assert (run_dir / "artifacts" / "transcript.json").exists()
    assert (run_dir / "artifacts" / "minutes.json").exists()
    assert (run_dir / "artifacts" / "minutes.md").exists()
    assert (run_dir / "artifacts" / "truth_gate_report.json").exists()
    # PDF location (either exports or artifacts depending on renderer path)
    pdf1 = run_dir / "exports" / "minutes.pdf"
    pdf2 = run_dir / "artifacts" / "minutes.pdf"
    assert pdf1.exists() or pdf2.exists()

    md = (run_dir / "artifacts" / "minutes.md").read_text(encoding="utf-8")
    assert _normalize_md(md) == MEETING_GOLDEN


def test_e2e_journal_outputs_exist_and_match_golden(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="journal", title="j")

    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(session_id=ses, plan={"steps": [{"name": "formalize", "params": {"mode": "journal"}}]})
    res = run_job(run_id)
    assert res.ok is True and res.status == "succeeded"

    run_dir = root / "runs" / run_id
    assert (run_dir / "artifacts" / "transcript.json").exists()
    assert (run_dir / "artifacts" / "journal.json").exists()
    assert (run_dir / "artifacts" / "journal.md").exists()
    assert (run_dir / "artifacts" / "truth_gate_report.json").exists()

    pdf1 = run_dir / "exports" / "journal.pdf"
    pdf2 = run_dir / "artifacts" / "journal.pdf"
    assert pdf1.exists() or pdf2.exists()

    md = (run_dir / "artifacts" / "journal.md").read_text(encoding="utf-8")
    assert _normalize_md(md) == JOURNAL_GOLDEN


def test_truth_gate_blocks_uncited_decision(tmp_path: Path, monkeypatch) -> None:
    """Negative truth test: any decision/action item MUST have non-empty citations."""
    import ashby.modules.meetings.pipeline.job_runner as job_runner
    from ashby.modules.meetings.hashing import sha256_file

    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(session_id=ses, plan={"steps": [{"name": "formalize", "params": {"mode": "meeting"}}]})

    def _bad_minutes(run_dir: Path, template_id: str, retention: str):
        artifacts = run_dir / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        out_path = artifacts / "minutes.json"
        payload = {
            "version": 1,
            "session_id": "",
            "run_id": run_dir.name,
            "header": {
                "title": "Meeting Minutes",
                "mode": "meeting",
                "retention": retention,
                "template_id": template_id,
                "created_ts": time.time(),
                "engine": "test_bad_minutes_uncited",
            },
            "participants": [{"speaker_label": "SPEAKER_00"}],
            "topics": [],
            "decisions": [
                {
                    "decision_id": "d1",
                    "title": "We decided a thing",
                    "summary": "",
                    "citations": [],  # invalid: must be non-empty
                }
            ],
            "action_items": [],
            "notes": [],
            "open_questions": [],
        }
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "kind": "minutes_json",
            "path": str(out_path),
            "sha256": sha256_file(out_path),
            "created_ts": time.time(),
            "engine": "test_bad_minutes_uncited",
        }

    monkeypatch.setattr(job_runner, "formalize_meeting_to_minutes_json", _bad_minutes)

    res = job_runner.run_job(run_id)
    assert res.ok is False
    assert res.status == "failed"

    run_dir = root / "runs" / run_id
    report_path = run_dir / "artifacts" / "truth_gate_report.json"
    assert report_path.exists()

    # No publish on blocked: MD/PDF must not exist.
    assert not (run_dir / "artifacts" / "minutes.md").exists()
    assert not (run_dir / "exports" / "minutes.pdf").exists()


def test_minutes_json_refuses_overwrite(tmp_path: Path) -> None:
    """Negative overwrite test: minutes.json write-once enforcement."""
    from ashby.modules.meetings.formalize.minutes_json import formalize_meeting_to_minutes_json

    run_dir = tmp_path / "run_000"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    # Minimal transcript.json payload (segments from fixture)
    fixture = Path(__file__).parent / "fixtures" / "stub_transcript_segments.json"
    segs = json.loads(fixture.read_text(encoding="utf-8"))
    transcript = {
        "version": 1,
        "session_id": "",
        "run_id": run_dir.name,
        "mode": "meeting",
        "segments": segs,
    }
    (artifacts / "transcript.json").write_text(json.dumps(transcript, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # First write OK
    formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")

    # Second write must refuse
    with pytest.raises(FileExistsError):
        formalize_meeting_to_minutes_json(run_dir, template_id="default", retention="MED")
