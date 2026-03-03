from __future__ import annotations

import time
import os
import json
from pathlib import Path
from typing import Any, Dict, Tuple

from ashby.modules.meetings.store import sha256_file
from ashby.modules.meetings.render.export_pdf import export_pdf_stub


def _vtuple(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in (raw or "").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out or [0])


def _weasyprint_import() -> Tuple[bool, str]:
    try:
        import weasyprint  # noqa: F401
        import pydyf  # type: ignore

        wv = _vtuple(getattr(weasyprint, "__version__", "0"))
        pv = _vtuple(getattr(pydyf, "__version__", "0"))
        # Known incompatibility:
        # WeasyPrint 60-62 + pydyf >= 0.11 can fail at runtime with:
        # "AttributeError: 'super' object has no attribute 'transform'"
        if (60, 0) <= wv < (63, 0) and pv >= (0, 11):
            return (
                False,
                f"Incompatible versions: weasyprint={getattr(weasyprint,'__version__','?')} "
                f"with pydyf={getattr(pydyf,'__version__','?')}. "
                "Install pydyf<0.11 for WeasyPrint<63.",
            )
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _render_weasyprint(md_text: str, out_path: Path, *, footer_text: str = "") -> None:
    footer_html = ""
    if footer_text:
        safe_footer = (
            footer_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        footer_html = f"<div class='footer'>{safe_footer}</div>"
    html = (
        "<html><head><meta charset='utf-8'>"
        "<style>"
        "body{font-family:sans-serif;margin:24px 24px 36px 24px;}"
        "pre{white-space:pre-wrap;}"
        ".footer{position:fixed;bottom:8px;left:24px;right:24px;font-size:9px;color:#6b7280;}"
        "</style>"
        "</head><body><pre>"
        + md_text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        + "</pre>"
        + footer_html
        + "</body></html>"
    )
    from weasyprint import HTML
    HTML(string=html).write_pdf(str(out_path))


def render_pdf_adapter(run_dir: Path, *, md_path: Path, out_name: str = "formalized.pdf") -> Dict[str, Any]:
    """Render a print-ready PDF from an MD artifact.

    v1 behavior:
    - Prefer WeasyPrint if available.
    - Fall back to a truthful stub renderer if WeasyPrint is unavailable or errors.
    - Refuse overwrite (write-once).
    - Output naming is caller-controlled via out_name (Codex contract).
    """
    # Opt-in fast mode: force stub PDF rendering to keep test/runtime loops quick.
    # Production behavior remains unchanged unless ASHBY_FAST_TESTS is set.
    fast_tests = (os.environ.get("ASHBY_FAST_TESTS") or "").strip().lower() in {"1", "true", "yes"}

    exports = run_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)

    out_path = exports / out_name
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite PDF: {out_path}")

    if not md_path.exists():
        raise FileNotFoundError(f"Missing md_path: {md_path}")

    kind = f"{Path(out_name).stem}_pdf"
    run_meta = {}
    run_json = run_dir / "run.json"
    if run_json.exists():
        try:
            run_meta = json.loads(run_json.read_text(encoding="utf-8"))
        except Exception:
            run_meta = {}
    session_id = str(run_meta.get("session_id") or "").strip() or "unknown_session"
    formalization_id = str(run_meta.get("run_id") or run_dir.name).strip() or run_dir.name
    created_raw = run_meta.get("created_ts")
    created = str(float(created_raw)) if isinstance(created_raw, (int, float)) else "unknown"
    footer = f"session:{session_id}  formalization:{formalization_id}  created:{created}"

    if fast_tests:
        out = export_pdf_stub(run_dir, md_path=md_path, out_name=out_name, footer_text=footer)
        out["warning"] = "ASHBY_FAST_TESTS enabled; forced stub PDF renderer."
        return out

    ok, why = _weasyprint_import()
    if ok:
        try:
            md_text = md_path.read_text(encoding="utf-8", errors="replace")
            _render_weasyprint(md_text, out_path, footer_text=footer)
            return {
                "kind": kind,
                "path": str(out_path),
                "sha256": sha256_file(out_path),
                "created_ts": time.time(),
                "engine": "weasyprint",
                "source_md": str(md_path),
                "out_name": out_name,
            }
        except Exception as e:
            why = f"WeasyPrint runtime error: {type(e).__name__}: {e}"

    # Fallback: built-in text PDF renderer (truthful)
    out = export_pdf_stub(run_dir, md_path=md_path, out_name=out_name, footer_text=footer)
    out["warning"] = why or "WeasyPrint unavailable; used built-in text PDF renderer."
    return out
