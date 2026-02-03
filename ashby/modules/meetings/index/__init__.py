"""Stuart retrieval/indexing primitives.

QUEST_022 introduces deterministic SQLite FTS indexing.
QUEST_023 will build the query UX + citation rendering on top.
"""

from .ingest import ingest_run
from .sqlite_fts import SearchHit, connect, ensure_schema, get_db_path, search

__all__ = [
    "SearchHit",
    "connect",
    "ensure_schema",
    "get_db_path",
    "ingest_run",
    "search",
]
