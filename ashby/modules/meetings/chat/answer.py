from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple
import uuid

from ashby.modules.llm import HTTPGatewayLLMService, LLMChatEvidenceSegment, LLMChatRequest
from ashby.modules.meetings.observability import events as obs_events
from ashby.modules.meetings.chat.retrieval import EvidenceSegment, RetrievedHit
from ashby.modules.meetings.schemas.chat import (
    ChatHitV1,
    ChatReplyV1,
    parse_chat_action_v1,
)
from ashby.modules.meetings.schemas.search import CitationAnchor


def _anchor_key(session_id: str, run_id: str, segment_id: int) -> Tuple[str, str, int]:
    return (str(session_id), str(run_id), int(segment_id))


def _evidence_anchor(seg: EvidenceSegment) -> CitationAnchor:
    return CitationAnchor(
        session_id=seg.session_id,
        run_id=seg.run_id,
        segment_id=int(seg.segment_id),
        speaker_label=seg.speaker_label,
        t_start=seg.t_start,
        t_end=seg.t_end,
        source_path=seg.source_path,
    )


def _hit_to_chat_hit(hit: RetrievedHit) -> ChatHitV1:
    return ChatHitV1(
        session_id=hit.session_id,
        run_id=hit.run_id,
        snippet=hit.snippet,
        score=float(hit.score),
        match_kind=hit.match_kind,
        citation=CitationAnchor(
            session_id=hit.session_id,
            run_id=hit.run_id,
            segment_id=int(hit.segment_id),
            speaker_label=hit.speaker_label,
            t_start=hit.t_start,
            t_end=hit.t_end,
            source_path=hit.source_path,
        ),
    )


def _retrieval_only_text(question: str, evidence: List[EvidenceSegment]) -> str:
    q = (question or "").strip()
    if not evidence:
        if q:
            return f"I can't verify an answer from available evidence for: \"{q}\"."
        return "I can't verify an answer from available evidence."
    lines = ["I can only answer from retrieved evidence. Top evidence:"]
    for seg in evidence[:3]:
        snippet = " ".join((seg.text or "").split())
        if len(snippet) > 180:
            snippet = snippet[:177] + "..."
        lines.append(f"- [{seg.session_id}#{seg.segment_id}] {snippet}")
    return "\n".join(lines)


def _build_llm_request(
    *,
    question: str,
    scope: str,
    ui_state: Dict[str, Any],
    history_tail: List[Dict[str, Any]],
    evidence_segments: List[EvidenceSegment],
) -> LLMChatRequest:
    rows = [
        LLMChatEvidenceSegment(
            session_id=s.session_id,
            run_id=s.run_id,
            segment_id=int(s.segment_id),
            text=s.text,
            speaker_label=s.speaker_label,
            t_start=s.t_start,
            t_end=s.t_end,
            source_path=s.source_path,
        )
        for s in evidence_segments
    ]
    return LLMChatRequest(
        question=question,
        scope=scope,
        ui_state=dict(ui_state or {}),
        history_tail=[dict(x) for x in (history_tail or []) if isinstance(x, dict)],
        evidence_segments=rows,
    )


def _extract_output(output_json: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    text = str(output_json.get("text") or "").strip()
    citations = output_json.get("citations") if isinstance(output_json.get("citations"), list) else []
    actions = output_json.get("actions") if isinstance(output_json.get("actions"), list) else []
    return text, [c for c in citations if isinstance(c, dict)], [a for a in actions if isinstance(a, dict)]


def answer_with_evidence(
    *,
    question: str,
    scope: str,
    ui_state: Optional[Dict[str, Any]],
    history_tail: Optional[List[Dict[str, Any]]],
    evidence_segments: List[EvidenceSegment],
    hits: List[RetrievedHit],
    llm_service: Optional[HTTPGatewayLLMService] = None,
) -> ChatReplyV1:
    ui = dict(ui_state or {})
    focus_session_id = str(ui.get("selected_session_id") or "").strip() or None
    correlation_id = str(ui.get("correlation_id") or "").strip() or str(uuid.uuid4())
    run_id = str(ui.get("active_run_id") or "").strip() or None

    evidence_by_key = {_anchor_key(s.session_id, s.run_id, int(s.segment_id)): s for s in evidence_segments}

    hit_rows = [_hit_to_chat_hit(h) for h in hits]
    fallback_citations = [_evidence_anchor(s) for s in evidence_segments[:5]]

    # Local-only profile short-circuits LLM synthesis.
    profile = str(ui.get("profile") or ui.get("selected_profile") or "").strip().upper()
    if profile == "LOCAL_ONLY":
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="llm",
            event="llm.disabled",
            summary="LLM disabled for LOCAL_ONLY chat profile",
            correlation_id=correlation_id,
            session_id=focus_session_id,
            run_id=run_id,
            trace_id=correlation_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"reason": "LOCAL_ONLY"},
        )
        obs_events.emit_alert(
            level="WARNING",
            source="backend",
            component="llm",
            event="alert.llm_disabled_on_chat",
            summary="LLM disabled while handling chat request",
            correlation_id=correlation_id,
            session_id=focus_session_id,
            run_id=run_id,
            trace_id=correlation_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"reason": "LOCAL_ONLY"},
        )
        return ChatReplyV1(
            kind="assistant",
            text=_retrieval_only_text(question, evidence_segments),
            citations=fallback_citations,
            hits=hit_rows,
            actions=[],
        )

    if not evidence_segments:
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="llm",
            event="llm.fallback",
            summary="No evidence segments available; returning retrieval-only response",
            correlation_id=correlation_id,
            session_id=focus_session_id,
            run_id=run_id,
            trace_id=correlation_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"reason": "no_evidence_segments"},
        )
        return ChatReplyV1(
            kind="assistant",
            text=_retrieval_only_text(question, evidence_segments),
            citations=[],
            hits=hit_rows,
            actions=[],
        )

    service = llm_service or HTTPGatewayLLMService()
    disclosure: List[str] = []

    try:
        req = _build_llm_request(
            question=question,
            scope=scope,
            ui_state=ui,
            history_tail=list(history_tail or []),
            evidence_segments=evidence_segments,
        )
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="llm",
            event="llm.call",
            summary="Invoking LLM chat gateway",
            correlation_id=correlation_id,
            session_id=focus_session_id,
            run_id=run_id,
            trace_id=correlation_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"provider": "http_gateway", "model": "gateway_chat"},
        )
        llm_resp = service.chat(req)
        obs_events.emit_event(
            level="INFO",
            source="backend",
            component="llm",
            event="llm.response",
            summary="LLM chat response received",
            correlation_id=correlation_id,
            session_id=focus_session_id,
            run_id=run_id,
            trace_id=correlation_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={
                "provider": llm_resp.provider,
                "model": llm_resp.model,
                "timing_ms": int(llm_resp.timing_ms or 0),
                "usage": llm_resp.usage if isinstance(llm_resp.usage, dict) else {},
            },
        )
        text, raw_citations, raw_actions = _extract_output(llm_resp.output_json)
    except Exception as exc:
        obs_events.emit_event(
            level="ERROR",
            source="backend",
            component="llm",
            event="llm.error",
            summary="LLM chat call failed",
            correlation_id=correlation_id,
            session_id=focus_session_id,
            run_id=run_id,
            trace_id=correlation_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"reason": f"{type(exc).__name__}: {exc}"},
        )
        obs_events.emit_alert(
            level="ERROR",
            source="backend",
            component="llm",
            event="alert.llm_error",
            summary="LLM chat call failed",
            correlation_id=correlation_id,
            session_id=focus_session_id,
            run_id=run_id,
            trace_id=correlation_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"reason": f"{type(exc).__name__}: {exc}"},
        )
        obs_events.emit_event(
            level="WARNING",
            source="backend",
            component="llm",
            event="llm.fallback",
            summary="Fallback to retrieval-only chat response",
            correlation_id=correlation_id,
            session_id=focus_session_id,
            run_id=run_id,
            trace_id=correlation_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=None,
            data={"reason": "llm_error"},
        )
        return ChatReplyV1(
            kind="assistant",
            text=_retrieval_only_text(question, evidence_segments),
            citations=fallback_citations,
            hits=hit_rows,
            actions=[],
        )

    valid_citations: List[CitationAnchor] = []
    for row in raw_citations:
        try:
            sid = str(row.get("session_id") or "").strip()
            rid = str(row.get("run_id") or "").strip()
            seg_id = int(row.get("segment_id"))
        except Exception:
            continue
        key = _anchor_key(sid, rid, seg_id)
        seg = evidence_by_key.get(key)
        if seg is None:
            disclosure.append("Removed citation outside retrieved evidence.")
            continue
        valid_citations.append(
            CitationAnchor(
                session_id=sid,
                run_id=rid,
                segment_id=seg_id,
                speaker_label=str(row.get("speaker_label") or seg.speaker_label or "").strip() or None,
                t_start=(float(row.get("t_start_ms")) / 1000.0 if isinstance(row.get("t_start_ms"), int) else seg.t_start),
                t_end=(float(row.get("t_end_ms")) / 1000.0 if isinstance(row.get("t_end_ms"), int) else seg.t_end),
                source_path=seg.source_path,
            )
        )

    valid_actions = []
    for row in raw_actions:
        try:
            action = parse_chat_action_v1(row)
        except Exception:
            disclosure.append("Removed invalid action payload.")
            continue
        ad = asdict(action)
        if ad.get("kind") == "jump_to_segment":
            sid = str(ad.get("session_id") or "")
            seg_id = int(ad.get("segment_id") or -1)
            exists = any(s.session_id == sid and int(s.segment_id) == seg_id for s in evidence_segments)
            if not exists:
                disclosure.append("Removed jump action outside retrieved evidence.")
                continue
        valid_actions.append(action)

    if text and not valid_citations:
        disclosure.append("Insufficient cited evidence for model answer; returning retrieval-only response.")
        return ChatReplyV1(
            kind="assistant",
            text=_retrieval_only_text(question, evidence_segments),
            citations=fallback_citations,
            hits=hit_rows,
            actions=[],
        )

    if scope == "global" and focus_session_id:
        external = [c for c in valid_citations if c.session_id != focus_session_id]
        if external:
            disclosure.append(f"Found evidence outside focused session {focus_session_id}.")

    final_text = (text or "").strip() or _retrieval_only_text(question, evidence_segments)
    if disclosure:
        final_text = f"{final_text}\n\nDisclosure: {' '.join(sorted(set(disclosure)))}"

    return ChatReplyV1(
        kind="assistant",
        text=final_text,
        citations=valid_citations if valid_citations else fallback_citations,
        hits=hit_rows,
        actions=valid_actions,
    )
