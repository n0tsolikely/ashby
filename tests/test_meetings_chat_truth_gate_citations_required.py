from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ashby.modules.meetings.chat.answer import answer_with_evidence
from ashby.modules.meetings.chat.retrieval import EvidenceSegment, RetrievedHit


@dataclass
class _Resp:
    output_json: Dict[str, Any]


class _FakeLLM:
    def chat(self, _request: Any, *, artifacts_dir: Any = None) -> _Resp:
        return _Resp(output_json={"text": "Strong claim", "citations": [], "actions": []})


def test_truth_gate_requires_citations() -> None:
    evidence = [
        EvidenceSegment(
            session_id="ses_1",
            run_id="run_1",
            segment_id=1,
            text="source fact",
            speaker_label="SPEAKER_00",
            t_start=0.0,
            t_end=1.0,
            source_path="x",
            match_kind="MENTION_MATCH",
        )
    ]
    hits = [
        RetrievedHit(
            session_id="ses_1",
            run_id="run_1",
            segment_id=1,
            snippet="source fact",
            score=0.1,
            title="t",
            mode="meeting",
            speaker_label="SPEAKER_00",
            t_start=0.0,
            t_end=1.0,
            source_path="x",
            match_kind="MENTION_MATCH",
        )
    ]
    reply = answer_with_evidence(
        question="q",
        scope="session",
        ui_state={"selected_session_id": "ses_1"},
        history_tail=[],
        evidence_segments=evidence,
        hits=hits,
        llm_service=_FakeLLM(),  # type: ignore[arg-type]
    )
    assert "evidence" in reply.text.lower()
    assert reply.citations
