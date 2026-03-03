from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.hashing import sha256_file


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _normalize_text(md_text: str) -> list[str]:
    # Keep renderer deterministic and dependency-free.
    # We wrap long lines so content is visible in a standard Letter page.
    out: list[str] = []
    for raw in (md_text or "").splitlines():
        line = raw.rstrip()
        if not line:
            out.append("")
            continue
        while len(line) > 110:
            out.append(line[:110])
            line = line[110:]
        out.append(line)
    return out or ["(empty document)"]


def _build_text_pdf_bytes(
    md_text: str,
    title: str = "Stuart Formalization",
    *,
    footer_text: Optional[str] = None,
) -> bytes:
    lines = _normalize_text(md_text)
    lines_per_page = 58
    pages = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)]
    if not pages:
        pages = [["(empty document)"]]

    objects: dict[int, bytes] = {}
    # 1: catalog, 2: pages root, 3: font
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    kids: list[str] = []
    next_id = 4
    for page_lines in pages:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        kids.append(f"{page_id} 0 R")

        stream_lines = [
            "BT",
            "/F1 10 Tf",
            "72 770 Td",
            "12 TL",
            f"({_pdf_escape(title)}) Tj",
            "T*",
            "T*",
        ]
        for ln in page_lines:
            stream_lines.append(f"({_pdf_escape(ln)}) Tj")
            stream_lines.append("T*")

        if footer_text:
            stream_lines.extend(
                [
                    "ET",
                    "BT",
                    "/F1 8 Tf",
                    "72 28 Td",
                    f"({_pdf_escape(footer_text)}) Tj",
                ]
            )
        stream_lines.append("ET")
        stream_text = "\n".join(stream_lines) + "\n"
        stream_bytes = stream_text.encode("latin-1", errors="replace")

        objects[content_id] = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"endstream"
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")

    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode("ascii")
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    max_obj = max(objects.keys())
    chunks: list[bytes] = [b"%PDF-1.4\n"]
    offsets: dict[int, int] = {}
    offset = len(chunks[0])

    for obj_id in range(1, max_obj + 1):
        body = objects[obj_id]
        header = f"{obj_id} 0 obj\n".encode("ascii")
        footer = b"\nendobj\n"
        offsets[obj_id] = offset
        chunks.extend([header, body, footer])
        offset += len(header) + len(body) + len(footer)

    xref_start = offset
    xref = [f"xref\n0 {max_obj + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for obj_id in range(1, max_obj + 1):
        xref.append(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    ).encode("ascii")
    chunks.extend(xref)
    chunks.append(trailer)
    return b"".join(chunks)


def export_pdf_stub(
    run_dir: Path,
    *,
    md_path: Optional[Path] = None,
    out_name: str = "formalized.pdf",
    footer_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Export dependency-free content PDF.

    Used as a fallback renderer when richer engines are unavailable.

    Rules:
    - Writes to run_dir/exports/<out_name>
    - Refuses overwrite (write-once)
    - Artifact kind is derived from filename stem: <stem>_pdf
      (e.g., minutes.pdf -> minutes_pdf)
    """
    exports_dir = run_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    out_path = exports_dir / out_name
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite PDF: {out_path}")

    md_text = ""
    if md_path and md_path.exists():
        md_text = md_path.read_text(encoding="utf-8", errors="replace")
    pdf_bytes = _build_text_pdf_bytes(
        md_text or "No content available.",
        title=Path(out_name).stem.replace("_", " ").title(),
        footer_text=footer_text or None,
    )
    out_path.write_bytes(pdf_bytes)

    h = sha256_file(out_path)
    kind = f"{Path(out_name).stem}_pdf"
    return {
        "kind": kind,
        "path": str(out_path),
        "sha256": h,
        "mime": "application/pdf",
        "created_ts": time.time(),
        "engine": "builtin_text_pdf",
        "source_md": str(md_path) if md_path else None,
        "out_name": out_name,
    }
