from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CitationAnchor:
    """Pointer back to a ground-truth transcript segment.

    Anchor discipline:
    - segment_id is the stable pointer (from transcript.json/aligned_transcript.json)
      or legacy transcript.txt line anchor.
    - t_start/t_end are optional timestamp hints (seconds) when available.
    """

    session_id: str
    run_id: str
    segment_id: int

    speaker_label: Optional[str] = None
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    source_path: Optional[str] = None

    kind: str = "transcript_segment"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "segment_id": int(self.segment_id),
            "speaker_label": self.speaker_label,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "source_path": self.source_path,
        }


@dataclass(frozen=True)
class SearchResultItem:
    rank: int
    score: float
    snippet: str
    title: Optional[str]
    mode: Optional[str]
    citation: CitationAnchor

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": int(self.rank),
            "score": float(self.score),
            "snippet": self.snippet,
            "title": self.title,
            "mode": self.mode,
            "citation": self.citation.to_dict(),
        }


@dataclass(frozen=True)
class SearchResults:
    """Door-agnostic search response (web/telegram/cli)."""

    query: str
    limit: int
    total_hits: int
    session_filter: Optional[str] = None
    mode_filter: Optional[str] = None
    results: List[SearchResultItem] = field(default_factory=list)

    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "limit": int(self.limit),
            "total_hits": int(self.total_hits),
            "session_filter": self.session_filter,
            "mode_filter": self.mode_filter,
            "results": [r.to_dict() for r in self.results],
            "message": self.message,
        }
