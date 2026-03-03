from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ImportedTemplateDraft:
    mode: str
    template_title: str
    template_text: str
    defaults: Dict[str, bool]


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        return ""
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            parts.append((page.extract_text() or "").strip())
        return "\n".join([p for p in parts if p]).strip()
    except Exception:
        return ""


def draft_from_source_text(
    mode: str,
    title: str,
    source_text: str,
    llm_service: Optional[object] = None,
) -> ImportedTemplateDraft:
    # Seam for future LLM-assisted drafting (QUEST_195+).
    del llm_service
    clean_title = (title or "").strip() or "Imported Template"
    clean_text = (source_text or "").strip()
    if not clean_text:
        clean_text = "Overview\nAction Items\nDecisions"

    lines = [ln.strip() for ln in clean_text.splitlines() if ln.strip()]
    headings = []
    for line in lines:
        token = line.rstrip(":")
        if 2 <= len(token) <= 64 and len(token.split()) <= 8:
            headings.append(token)
        if len(headings) >= 8:
            break

    if not headings:
        headings = ["Overview", "Key Points", "Action Items"]
    if mode == "journal" and "Narrative" not in headings:
        headings.insert(0, "Narrative")

    body = "\n\n".join(f"## {h}" for h in headings)
    template_text = (
        "---\n"
        "template_version: 1\n"
        "defaults:\n"
        "  include_citations: false\n"
        "  show_empty_sections: false\n"
        "---\n\n"
        f"{body}\n"
    )
    return ImportedTemplateDraft(
        mode=mode,
        template_title=clean_title,
        template_text=template_text,
        defaults={"include_citations": False, "show_empty_sections": False},
    )
