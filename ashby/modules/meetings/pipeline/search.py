from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.index.sqlite_fts import connect, ensure_schema, get_db_path, search
from ashby.modules.meetings.schemas.search import CitationAnchor, SearchResultItem, SearchResults


def search_and_write_results(
    run_dir: Path,
    *,
    query: str,
    session_id: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Execute deterministic keyword search and write door-agnostic results artifact.

    Artifact: <run_dir>/artifacts/search_results.json
    """
    q = (query or "").strip()
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    out_path = artifacts_dir / "search_results.json"

    lay = init_stuart_root()
    db_path = get_db_path(stuart_root=lay.root)

    conn = connect(db_path)
    try:
        ensure_schema(conn)
        hits = search(conn, q, limit=int(limit), session_id=session_id)
    finally:
        conn.close()

    items = []
    for i, h in enumerate(hits, start=1):
        cite = CitationAnchor(
            session_id=h.session_id,
            run_id=h.run_id,
            segment_id=int(h.segment_id),
            speaker_label=h.speaker_label,
            t_start=h.t_start,
            t_end=h.t_end,
            source_path=h.source_path,
        )
        items.append(
            SearchResultItem(
                rank=i,
                score=float(h.score),
                snippet=h.snippet,
                title=h.title,
                mode=h.mode,
                citation=cite,
            )
        )

    msg = None
    if not q:
        msg = "Empty query."
    elif len(items) == 0:
        msg = "No hits found."

    payload = SearchResults(
        query=q,
        limit=int(limit),
        total_hits=len(items),
        results=items,
        message=msg,
    )

    out_path.write_text(json.dumps(payload.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    h = sha256_file(out_path)
    return {
        "kind": "search_results",
        "path": str(out_path),
        "sha256": h,
        "mime": "application/json",
        "created_ts": time.time(),
        "query": q,
        "total_hits": len(items),
    }
