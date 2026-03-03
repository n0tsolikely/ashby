from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.schemas.artifacts_v1 import dump_json
from ashby.modules.meetings.schemas.evidence_map_v2 import validate_evidence_map_v2


def persist_llm_evidence_map(*, artifacts_dir: Path, evidence_map: Dict[str, Any]) -> Optional[Path]:
    if not evidence_map:
        return None
    validate_evidence_map_v2(evidence_map)
    out = artifacts_dir / "evidence_map_llm.json"
    dump_json(out, evidence_map, write_once=True)
    return out

