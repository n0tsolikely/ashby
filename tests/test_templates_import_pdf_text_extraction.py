from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from ashby.modules.meetings.templates.importer import extract_text_from_pdf


def _build_pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font_obj = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font_obj)  # noqa: SLF001
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): font_ref,
                }
            )
        }
    )
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 14 Tf 36 120 Td ({text}) Tj ET".encode("utf-8"))
    stream_ref = writer._add_object(stream)  # noqa: SLF001
    page[NameObject("/Contents")] = stream_ref
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_extract_text_from_pdf_returns_text() -> None:
    pdf_bytes = _build_pdf_with_text("Hello Template Import")
    extracted = extract_text_from_pdf(pdf_bytes)
    assert "Hello Template Import" in extracted
