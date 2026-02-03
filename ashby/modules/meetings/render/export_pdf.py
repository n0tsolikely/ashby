from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from ashby.modules.meetings.hashing import sha256_file


_MIN_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
72 720 Td
(Stuart v1 PDF stub) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000010 00000 n
0000000062 00000 n
0000000117 00000 n
0000000211 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
320
%%EOF
"""


def export_pdf_stub(run_dir: Path, *, md_path: Optional[Path] = None, out_name: str = "formalized.pdf") -> Dict[str, Any]:
    """
    QUEST_021 v1: export placeholder PDF.
    Real PDF rendering comes later; this establishes export plumbing and evidence trail.
    """
    exports_dir = run_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    out_path = exports_dir / out_name
    if not out_path.exists():
        out_path.write_bytes(_MIN_PDF)

    h = sha256_file(out_path)
    kind = "formalized_pdf" if out_name == "formalized.pdf" else "pdf"
    return {
        "kind": kind,
        "path": str(out_path),
        "sha256": h,
        "mime": "application/pdf",
        "created_ts": time.time(),
        "source_md": str(md_path) if md_path else None,
    }
