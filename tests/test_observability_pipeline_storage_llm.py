from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ashby.modules.meetings.pipeline import job_runner as jr
from ashby.modules.meetings.chat.answer import answer_with_evidence
from ashby.modules.meetings.chat.retrieval import EvidenceSegment, RetrievedHit


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        rows.append(json.loads(ln))
    return rows


@dataclass
class _Layout:
    root: Path
    runs: Path
    overlays: Path


@dataclass
class _Resolved:
    contribution_id: str
    source_path: Path
    source_kind: str


class _MatrixFailNormalize:
    def normalize(self, run_dir: Path, source_path: Path):
        return {"kind": "normalized_audio", "path": str(run_dir / "artifacts" / "normalized.wav"), "sha256": "x"}

    def transcribe(self, run_dir: Path):
        raise RuntimeError("transcribe_failed")

    def diarize(self, run_dir: Path):
        return {"kind": "diarized", "path": str(run_dir / "artifacts" / "diarized.json"), "sha256": "x"}

    def align(self, run_dir: Path):
        return {"kind": "aligned", "path": str(run_dir / "artifacts" / "aligned.json"), "sha256": "x"}

class _MatrixFailTranscribe:
    def normalize(self, run_dir: Path, source_path: Path):
        return {"kind": "normalized_audio", "path": str(run_dir / "artifacts" / "normalized.wav"), "sha256": "x"}

    def transcribe(self, run_dir: Path):
        raise RuntimeError("transcribe_failed")


def test_storage_lookup_and_miss_events(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "rt"))

    run_id = "run_storage_1"
    artifacts = tmp_path / "rt" / "runs" / run_id / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "exists.txt").write_text("ok", encoding="utf-8")

    got = jr._get_run_artifact_path(run_id, "exists.txt")
    miss = jr._get_run_artifact_path(run_id, "missing.txt")

    assert got is not None
    assert miss is None

    rows = _read_jsonl(tmp_path / "rt" / "realtime_log" / "events.jsonl")
    assert any(r.get("event") == "storage.lookup" for r in rows)
    assert any(r.get("event") == "storage.lookup_miss" for r in rows)


@pytest.mark.asyncio
async def test_chat_llm_disabled_and_error_alerts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "rt"))

    seg = EvidenceSegment(
        session_id="ses_1",
        run_id="run_1",
        segment_id=1,
        text="alpha",
        speaker_label="SPEAKER_00",
        t_start=0.0,
        t_end=1.0,
        source_path="runs/run_1/artifacts/transcript.json",
        match_kind="MENTION_MATCH",
    )
    hit = RetrievedHit(
        session_id="ses_1",
        run_id="run_1",
        segment_id=1,
        snippet="alpha",
        score=1.0,
        title="Session",
        mode="meeting",
        speaker_label="SPEAKER_00",
        t_start=0.0,
        t_end=1.0,
        source_path="runs/run_1/artifacts/transcript.json",
        match_kind="SEGMENT_TEXT",
    )

    reply_local = answer_with_evidence(
        question="q",
        scope="session",
        ui_state={"selected_session_id": "ses_1", "selected_profile": "LOCAL_ONLY", "correlation_id": "cid_local"},
        history_tail=[],
        evidence_segments=[seg],
        hits=[hit],
        llm_service=None,
    )
    assert isinstance(reply_local.text, str)

    class _FailService:
        def chat(self, request):
            raise RuntimeError("gateway_down")

    reply_fallback = answer_with_evidence(
        question="q",
        scope="session",
        ui_state={"selected_session_id": "ses_1", "selected_profile": "HYBRID", "correlation_id": "cid_err"},
        history_tail=[],
        evidence_segments=[seg],
        hits=[hit],
        llm_service=_FailService(),
    )
    assert isinstance(reply_fallback.text, str)

    events = _read_jsonl(tmp_path / "rt" / "realtime_log" / "events.jsonl")
    alerts = _read_jsonl(tmp_path / "rt" / "realtime_log" / "alerts.jsonl")
    assert any(r.get("event") == "llm.call" for r in events)
    assert any(r.get("event") == "llm.error" for r in events)
    assert not any(r.get("event") == "alert.llm_disabled_on_chat" for r in alerts)
    assert any(r.get("event") == "alert.llm_error" for r in alerts)


def test_pipeline_audio_missing_and_degraded_alert(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_EVENT_LOGGING", "1")
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "rt"))

    run_id = "run_pipe_1"
    run_dir = tmp_path / "rt" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "status": "queued",
        "session_id": "ses_1",
        "plan": {"steps": [{"kind": "transcribe", "params": {"mode": "meeting", "diarization_enabled": False}}]},
        "progress": 0,
    }

    def fake_get_run_state(_run_id: str):
        return dict(state)

    def fake_update_run_state(_run_id: str, **kwargs):
        state.update({k: v for k, v in kwargs.items() if v is not None})
        return dict(state)

    def fake_layout():
        root = tmp_path / "rt"
        return _Layout(root=root, runs=root / "runs", overlays=root / "overlays")

    def fake_resolve_input_contribution(**kwargs):
        return _Resolved(
            contribution_id="con_1",
            source_path=tmp_path / "rt" / "missing_audio.wav",
            source_kind="audio",
        )

    monkeypatch.setattr(jr, "get_run_state", fake_get_run_state)
    monkeypatch.setattr(jr, "update_run_state", fake_update_run_state)
    monkeypatch.setattr(jr, "init_stuart_root", fake_layout)
    monkeypatch.setattr(jr, "resolve_input_contribution", fake_resolve_input_contribution)
    monkeypatch.setattr(jr, "get_meetings_adapter_matrix", lambda profile: _MatrixFailTranscribe())
    monkeypatch.setattr(jr, "get_execution_profile", lambda: "LOCAL_ONLY")
    monkeypatch.setattr(jr, "load_session_state", lambda session_id: {})

    result = jr.run_job(run_id)
    assert result.ok is False

    events = _read_jsonl(tmp_path / "rt" / "realtime_log" / "events.jsonl")
    alerts = _read_jsonl(tmp_path / "rt" / "realtime_log" / "alerts.jsonl")
    assert any(r.get("event") == "audio.missing" for r in events)
    assert any(r.get("event") == "alert.audio_missing" for r in alerts)
    assert any(r.get("event") == "alert.pipeline_degraded" for r in alerts)
