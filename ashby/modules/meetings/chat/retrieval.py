from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ashby.modules.meetings.index import sqlite_fts
from ashby.modules.meetings.index.sqlite_fts import fetch_segments
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.schemas.search import MatchKind


@dataclass(frozen=True)
class RetrievedHit:
    session_id: str
    run_id: str
    segment_id: int
    snippet: str
    score: float
    title: Optional[str]
    mode: Optional[str]
    speaker_label: Optional[str]
    t_start: Optional[float]
    t_end: Optional[float]
    source_path: Optional[str]
    match_kind: MatchKind

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "segment_id": int(self.segment_id),
            "snippet": self.snippet,
            "score": float(self.score),
            "title": self.title,
            "mode": self.mode,
            "speaker_label": self.speaker_label,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "source_path": self.source_path,
            "match_kind": self.match_kind,
        }


@dataclass(frozen=True)
class EvidenceSegment:
    session_id: str
    run_id: str
    segment_id: int
    text: str
    speaker_label: Optional[str]
    t_start: Optional[float]
    t_end: Optional[float]
    source_path: Optional[str]
    match_kind: MatchKind

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "segment_id": int(self.segment_id),
            "text": self.text,
            "speaker_label": self.speaker_label,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "source_path": self.source_path,
            "match_kind": self.match_kind,
        }


def _db_conn():
    lay = init_stuart_root()
    db_path = sqlite_fts.get_db_path(stuart_root=lay.root)
    conn = sqlite_fts.connect(db_path)
    sqlite_fts.ensure_schema(conn)
    return conn


def retrieve_hits(query: str, *, session_id: Optional[str], limit: int = 8) -> List[RetrievedHit]:
    q = (query or "").strip()
    if not q:
        return []
    conn = _db_conn()
    try:
        rows = sqlite_fts.search(conn, q, limit=max(int(limit), 1), session_id=session_id)
    finally:
        conn.close()

    out: List[RetrievedHit] = []
    for r in rows:
        out.append(
            RetrievedHit(
                session_id=r.session_id,
                run_id=r.run_id,
                segment_id=int(r.segment_id),
                snippet=r.snippet,
                score=float(r.score),
                title=r.title,
                mode=r.mode,
                speaker_label=r.speaker_label,
                t_start=r.t_start,
                t_end=r.t_end,
                source_path=r.source_path,
                match_kind="MENTION_MATCH",
            )
        )
    return out


def hydrate_evidence(hits: List[RetrievedHit]) -> List[EvidenceSegment]:
    if not hits:
        return []
    by_run: Dict[str, List[RetrievedHit]] = {}
    for h in hits:
        by_run.setdefault(h.run_id, []).append(h)

    conn = _db_conn()
    try:
        out: List[EvidenceSegment] = []
        for run_id, run_hits in sorted(by_run.items(), key=lambda t: t[0]):
            seg_ids = sorted({int(h.segment_id) for h in run_hits})
            seg_rows = fetch_segments(conn, run_id=run_id, segment_ids=seg_ids)
            seg_by_id = {int(s.segment_id): s for s in seg_rows}
            for h in sorted(run_hits, key=lambda x: (x.run_id, x.segment_id)):
                seg = seg_by_id.get(int(h.segment_id))
                text = h.snippet
                speaker_label = h.speaker_label
                t_start = h.t_start
                t_end = h.t_end
                source_path = h.source_path
                if seg is not None:
                    text = seg.text
                    speaker_label = seg.speaker_label
                    t_start = seg.t_start
                    t_end = seg.t_end
                    source_path = seg.source_path
                out.append(
                    EvidenceSegment(
                        session_id=h.session_id,
                        run_id=h.run_id,
                        segment_id=int(h.segment_id),
                        text=text,
                        speaker_label=speaker_label,
                        t_start=t_start,
                        t_end=t_end,
                        source_path=source_path,
                        match_kind=h.match_kind,
                    )
                )
        return out
    finally:
        conn.close()


def attendee_sessions(name: str, *, limit: int = 12) -> List[Dict[str, Any]]:
    conn = _db_conn()
    try:
        rows = sqlite_fts.list_sessions_by_attendee(conn, name, limit=max(int(limit), 1))
    finally:
        conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "session_id": r.session_id,
                "title": r.title,
                "mode": r.mode,
                "created_ts": r.created_ts,
                "latest_run_id": r.latest_run_id,
                "match_kind": "ATTENDEE_MATCH",
            }
        )
    return out


def resolve_session_ref(token: str, sessions_index: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw = str(token or "").strip()
    if not raw:
        return []
    needle = raw.lower()

    exact_id = [s for s in sessions_index if str(s.get("session_id") or "").strip().lower() == needle]
    if exact_id:
        return [{**s, "match_kind": "ID_MATCH"} for s in exact_id]

    prefix_id = [s for s in sessions_index if str(s.get("session_id") or "").strip().lower().startswith(needle)]
    if len(prefix_id) == 1:
        return [{**prefix_id[0], "match_kind": "ID_MATCH"}]
    if len(prefix_id) > 1:
        return [{**s, "match_kind": "ID_MATCH"} for s in prefix_id]

    exact_title = [s for s in sessions_index if str(s.get("title") or "").strip().lower() == needle]
    if exact_title:
        return [{**s, "match_kind": "TITLE_MATCH"} for s in exact_title]

    contains = [s for s in sessions_index if needle in str(s.get("title") or "").strip().lower()]
    return [{**s, "match_kind": "TITLE_MATCH"} for s in contains]

