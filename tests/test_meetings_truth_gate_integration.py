from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import ashby.modules.meetings.pipeline.job_runner as job_runner
from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.store import add_contribution, create_run, create_session, get_run_state


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


def test_truth_gate_report_written_on_successful_run(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"name": "formalize", "params": {"mode": "meeting"}}]},
    )

    res = job_runner.run_job(run_id)
    assert res.ok is True
    assert res.status == "succeeded"

    report_path = root / "runs" / run_id / "artifacts" / "truth_gate_report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report.get("policy_id") == "meetings_truth_policy_v1"
    decision = report.get("decision") or {}
    assert decision.get("allowed") is True
    assert decision.get("blocked") is False

    md = root / "runs" / run_id / "artifacts" / "minutes.md"
    assert md.exists()


def test_truth_gate_blocks_unknown_citation_segment_id(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"name": "formalize", "params": {"mode": "meeting"}}]},
    )

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
                "engine": "test_bad_minutes",
            },
            "participants": [{"speaker_label": "SPEAKER_00"}],
            "topics": [
                {
                    "topic_id": "topic_001",
                    "title": "Bad Topic",
                    "summary": "",
                    # segment_id=999 will not exist in the stub transcript
                    "citations": [{"segment_id": 999}],
                }
            ],
            "decisions": [],
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
            "engine": "test_bad_minutes",
        }

    monkeypatch.setattr(job_runner, "formalize_meeting_to_minutes_json", _bad_minutes)

    res = job_runner.run_job(run_id)
    assert res.ok is False
    assert res.status == "failed"

    run_dir = root / "runs" / run_id

    # Truth gate report MUST still be written (machine-readable) even when blocked.
    report_path = run_dir / "artifacts" / "truth_gate_report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    decision = report.get("decision") or {}
    assert decision.get("blocked") is True

    # No silent publish on FAIL: MD/PDF must not exist.
    assert not (run_dir / "artifacts" / "minutes.md").exists()
    assert not (run_dir / "exports" / "minutes.pdf").exists()

    # Manifest must include the truth gate report artifact.
    st = get_run_state(run_id)
    kinds = [a.get("kind") for a in st.get("artifacts") or []]
    assert "truth_gate_report" in kinds
