from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.primary_outputs import resolve_primary_outputs
from ashby.modules.meetings.store import add_contribution, create_run, create_session
from ashby.modules.meetings.pipeline.job_runner import run_job


def _gen_wav(path: Path, *, freq: int = 440) -> None:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not installed")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=0.2", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def test_resolve_primary_outputs_meeting(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    src = tmp_path / "src.wav"
    _gen_wav(src, freq=1200)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template": "default"}}]},
    )

    res = run_job(run_id)
    assert res.ok is True

    po = resolve_primary_outputs(run_id)
    assert po.get("mode") == "meeting"
    assert po["json"]["kind"] == "minutes_json"
    assert str(po["json"]["path"]).endswith("/artifacts/minutes.json")
    assert po["md"]["kind"] == "minutes_md"
    assert str(po["md"]["path"]).endswith("/artifacts/minutes.md")
    assert po["pdf"]["kind"] == "minutes_pdf"
    assert str(po["pdf"]["path"]).endswith("/exports/minutes.pdf")
    assert po["evidence_map"]["kind"] == "evidence_map"
    assert str(po["evidence_map"]["path"]).endswith("/artifacts/evidence_map.json")


def test_resolve_primary_outputs_journal(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="journal", title="j")

    src = tmp_path / "src.wav"
    _gen_wav(src, freq=700)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "journal", "template": "default"}}]},
    )

    res = run_job(run_id)
    assert res.ok is True

    po = resolve_primary_outputs(run_id)
    assert po.get("mode") == "journal"
    assert po["json"]["kind"] == "journal_json"
    assert str(po["json"]["path"]).endswith("/artifacts/journal.json")
    assert po["md"]["kind"] == "journal_md"
    assert str(po["md"]["path"]).endswith("/artifacts/journal.md")
    assert po["pdf"]["kind"] == "journal_pdf"
    assert str(po["pdf"]["path"]).endswith("/exports/journal.pdf")
    assert po["evidence_map"]["kind"] == "evidence_map"
    assert str(po["evidence_map"]["path"]).endswith("/artifacts/evidence_map.json")
