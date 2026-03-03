from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ashby.modules.meetings.chat.answer import answer_with_evidence
from ashby.modules.meetings.chat.retrieval import EvidenceSegment, RetrievedHit


@dataclass
class _FakeChatResp:
    output_json: Dict[str, Any]


class _FakeLLM:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def chat(self, _request: Any, *, artifacts_dir: Any = None) -> _FakeChatResp:
        return _FakeChatResp(output_json=self._payload)


def _evidence() -> list[EvidenceSegment]:
    return [
        EvidenceSegment(
            session_id="ses_1",
            run_id="run_1",
            segment_id=1,
            text="Alice decided to ship on Friday",
            speaker_label="SPEAKER_00",
            t_start=1.0,
            t_end=2.0,
            source_path="runs/run_1/artifacts/transcript.json",
            match_kind="MENTION_MATCH",
        )
    ]


def _hits() -> list[RetrievedHit]:
    return [
        RetrievedHit(
            session_id="ses_1",
            run_id="run_1",
            segment_id=1,
            snippet="ship on Friday",
            score=0.1,
            title="t",
            mode="meeting",
            speaker_label="SPEAKER_00",
            t_start=1.0,
            t_end=2.0,
            source_path="runs/run_1/artifacts/transcript.json",
            match_kind="MENTION_MATCH",
        )
    ]


def test_answerer_filters_invalid_citations() -> None:
    llm = _FakeLLM(
        {
            "text": "Answer",
            "citations": [
                {"session_id": "ses_bad", "run_id": "run_bad", "segment_id": 99},
                {"session_id": "ses_1", "run_id": "run_1", "segment_id": 1},
            ],
            "actions": [],
        }
    )
    reply = answer_with_evidence(
        question="q",
        scope="session",
        ui_state={"selected_session_id": "ses_1"},
        history_tail=[],
        evidence_segments=_evidence(),
        hits=_hits(),
        llm_service=llm,  # type: ignore[arg-type]
    )
    assert len(reply.citations) == 1
    assert reply.citations[0].session_id == "ses_1"


def test_answerer_degrades_when_no_citations_in_model_output() -> None:
    llm = _FakeLLM({"text": "Claim without cites", "citations": [], "actions": []})
    reply = answer_with_evidence(
        question="q",
        scope="session",
        ui_state={"selected_session_id": "ses_1"},
        history_tail=[],
        evidence_segments=_evidence(),
        hits=_hits(),
        llm_service=llm,  # type: ignore[arg-type]
    )
    assert "retrieved evidence" in reply.text.lower() or "evidence" in reply.text.lower()
    assert reply.citations
