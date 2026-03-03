from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.store import create_session, create_run, get_run_state, add_contribution
from ashby.modules.meetings.pipeline.job_runner import run_job


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


def test_formalize_renders_md_evidence_and_pdf(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    ses = create_session(mode="meeting", title="t")

    src = tmp_path / "src.wav"
    _gen_wav(src)
    add_contribution(session_id=ses, source_path=src, source_kind="audio")

    run_id = create_run(
        session_id=ses,
        plan={"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template": "default"}}]},
    )

    res = run_job(run_id)
    assert res.ok is True

    state = get_run_state(run_id)
    assert state["status"] == "succeeded"

    po = state.get("primary_outputs")
    assert isinstance(po, dict)
    assert po.get("mode") == "meeting"
    assert po.get("json") and po["json"]["kind"] == "minutes_json"
    assert str(po["json"]["path"]).endswith("/artifacts/minutes.json")
    assert po.get("md") and po["md"]["kind"] == "minutes_md"
    assert str(po["md"]["path"]).endswith("/artifacts/minutes.md")
    assert po.get("txt") and po["txt"]["kind"] == "minutes_txt"
    assert str(po["txt"]["path"]).endswith("/artifacts/minutes.txt")
    assert po.get("pdf") and po["pdf"]["kind"] == "minutes_pdf"
    assert str(po["pdf"]["path"]).endswith("/exports/minutes.pdf")
    assert po.get("evidence_map") and po["evidence_map"]["kind"] == "evidence_map"
    assert str(po["evidence_map"]["path"]).endswith("/artifacts/evidence_map.json")

    arts = state.get("artifacts") or []
    kinds = {a.get("kind") for a in arts}
    assert "transcript" in kinds
    assert "diarization" in kinds
    assert "minutes_json" in kinds
    assert "minutes_md" in kinds
    assert "minutes_txt" in kinds
    assert "formalized_md" not in kinds
    assert "evidence_map" in kinds
    assert "minutes_pdf" in kinds
    assert "formalized_pdf" not in kinds

    run_dir = root / "runs" / run_id
    md_path = run_dir / "artifacts" / "minutes.md"
    txt_path = run_dir / "artifacts" / "minutes.txt"
    minutes_path = run_dir / "artifacts" / "minutes.json"
    ev_path = run_dir / "artifacts" / "evidence_map.json"
    pdf_path = run_dir / "exports" / "minutes.pdf"

    assert md_path.exists()
    assert txt_path.exists()
    assert minutes_path.exists()
    assert not (run_dir / "artifacts" / "formalized.md").exists()

    md_txt = md_path.read_text(encoding="utf-8")
    txt_txt = txt_path.read_text(encoding="utf-8")
    assert "## Notes" in md_txt
    assert "SPEAKER_" in md_txt
    assert "## Notes" not in txt_txt
    assert "SPEAKER_" in txt_txt
    assert ev_path.exists()
    assert pdf_path.exists()
    assert not (run_dir / "exports" / "formalized.pdf").exists()

    payload = json.loads(ev_path.read_text(encoding="utf-8"))
    assert payload["version"] == 2
    assert "claims" in payload
