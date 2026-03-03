from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict

from ashby.modules.meetings.hashing import sha256_file


def _markdown_to_text(md_text: str) -> str:
    lines: list[str] = []
    for raw in (md_text or "").splitlines():
        line = raw.rstrip()
        if not line:
            lines.append("")
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*+]\s+", "- ", line)
        line = re.sub(r"^\s*\d+\.\s+", "- ", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        line = re.sub(r"_([^_]+)_", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        lines.append(line)
    text = "\n".join(lines).strip()
    return (text + "\n") if text else ""


def export_txt(run_dir: Path, *, md_path: Path, out_name: str) -> Dict[str, Any]:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    out_path = artifacts / out_name
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite TXT: {out_path}")
    if not md_path.exists():
        raise FileNotFoundError(f"Missing markdown source for TXT export: {md_path}")

    out_path.write_text(_markdown_to_text(md_path.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    kind = f"{Path(out_name).stem}_txt"
    return {
        "kind": kind,
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "mime": "text/plain",
        "created_ts": time.time(),
        "source_md": str(md_path),
        "out_name": out_name,
    }
