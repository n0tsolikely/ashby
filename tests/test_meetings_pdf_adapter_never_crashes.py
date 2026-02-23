from __future__ import annotations

from pathlib import Path
import pytest

from ashby.modules.meetings.render.pdf_weasyprint import render_pdf_adapter


def test_pdf_adapter_produces_pdf(tmp_path: Path):
    run_dir = tmp_path / "runs" / "run_x"
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    md = run_dir / "artifacts" / "minutes.md"
    md.write_text("# Hello\n\nThis is a test.\n", encoding="utf-8")

    art = render_pdf_adapter(run_dir, md_path=md, out_name="minutes.pdf")
    assert art["kind"] == "minutes_pdf"
    p = Path(art["path"])
    assert p.exists()
    assert p.suffix == ".pdf"
    assert art.get("engine") in ("weasyprint", "builtin_text_pdf")
