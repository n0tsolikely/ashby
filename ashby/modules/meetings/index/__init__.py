"""Stuart retrieval/indexing primitives.

QUEST_022 introduces deterministic SQLite FTS indexing.
QUEST_023 will build the query UX + citation rendering on top.
"""

from .ingest import ingest_run
from .sqlite_fts import (
    LibrarySession,
    SearchHit,
    SegmentRow,
    connect,
    ensure_schema,
    fetch_segments,
    get_db_path,
    list_sessions,
    list_sessions_by_attendee,
    search,
)

__all__ = [
    "LibrarySession",
    "SearchHit",
    "SegmentRow",
    "connect",
    "ensure_schema",
    "fetch_segments",
    "get_db_path",
    "ingest_run",
    "list_sessions",
    "list_sessions_by_attendee",
    "search",
]
