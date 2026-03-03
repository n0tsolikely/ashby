from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.render.export_pdf import export_pdf_stub
from ashby.modules.meetings.render.pdf_weasyprint import render_pdf_adapter


def test_export_pdf_stub_includes_footer_text(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_1"
    (run_dir / "exports").mkdir(parents=True, exist_ok=True)
    md_path = run_dir / "artifacts" / "minutes.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("# Minutes\n\nHello", encoding="utf-8")

    footer = "session:ses_1  transcript:trv_1  created:1.0"
    out = export_pdf_stub(run_dir, md_path=md_path, out_name="transcript.pdf", footer_text=footer)

    pdf_bytes = Path(out["path"]).read_bytes()
    assert b"session:ses_1" in pdf_bytes
    assert b"transcript:trv_1" in pdf_bytes


def test_render_pdf_adapter_adds_formalization_footer_in_fast_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASHBY_FAST_TESTS", "1")

    run_dir = tmp_path / "run_2"
    (run_dir / "exports").mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps({"session_id": "ses_2", "run_id": "run_2", "created_ts": 2.0}),
        encoding="utf-8",
    )
    md_path = run_dir / "artifacts" / "minutes.md"
    md_path.write_text("# Minutes\n\nBody", encoding="utf-8")

    out = render_pdf_adapter(run_dir, md_path=md_path, out_name="minutes.pdf")
    pdf_bytes = Path(out["path"]).read_bytes()

    assert b"session:ses_2" in pdf_bytes
    assert b"formalization:run_2" in pdf_bytes
    assert b"created:2.0" in pdf_bytes
