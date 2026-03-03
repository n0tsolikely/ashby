from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from ashby.interfaces.web.http_envelope import fail, ok
from ashby.interfaces.web.templates_models_v1 import (
    TemplateDescriptorV1,
    TemplateDraftV1,
    TemplateRecordV1,
)
from ashby.modules.meetings.mode_registry import validate_mode
from ashby.modules.meetings.template_registry import (
    load_template_spec,
    template_descriptors_for_mode,
)
from ashby.modules.meetings.templates import store as template_store
from ashby.modules.meetings.templates.importer import (
    draft_from_source_text,
    extract_text_from_pdf,
)

router = APIRouter()


def _normalize_mode_or_fail(mode: str):
    mv = validate_mode(mode)
    if not mv.ok or mv.canonical is None:
        return fail("INVALID_MODE", mv.message or "Invalid mode.", status=400)
    return mv.canonical


def _descriptor_to_v1(d) -> TemplateDescriptorV1:
    return TemplateDescriptorV1(
        template_id=d.template_id,
        template_title=d.template_title,
        template_version=d.template_version,
        mode=d.mode,
        source=d.source,
    )


def _record_from_spec(mode: str, template_id: str, version: Optional[int] = None) -> TemplateRecordV1:
    spec = load_template_spec(mode, template_id, version=version)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    source = "system"
    try:
        if version is not None:
            user_rec = template_store.load_template(template_id, mode, version)
        else:
            versions = template_store.list_versions(template_id, mode)
            user_rec = template_store.load_template(template_id, mode, max(versions)) if versions else None
        if user_rec is not None:
            source = "user"
            created_at = user_rec.created_at
            updated_at = user_rec.updated_at
    except Exception:
        pass

    descriptor = TemplateDescriptorV1(
        template_id=spec.template_id,
        template_title=spec.template_title,
        template_version=spec.template_version,
        mode=mode,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
    )
    return TemplateRecordV1(
        descriptor=descriptor,
        defaults={
            "include_citations": bool(spec.defaults.get("include_citations", False)),
            "show_empty_sections": bool(spec.defaults.get("show_empty_sections", False)),
        },
        created_at=created_at,
        updated_at=updated_at,
        template_text=spec.raw_text,
    )


@router.get("/templates")
async def api_templates_list(
    mode: str,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    mode_or_fail = _normalize_mode_or_fail(mode)
    if not isinstance(mode_or_fail, str):
        return mode_or_fail
    mode_canonical = mode_or_fail

    rows = template_descriptors_for_mode(mode_canonical)
    needle = (q or "").strip().lower()
    if needle:
        rows = [
            r for r in rows
            if needle in r.template_id.lower() or needle in r.template_title.lower()
        ]
    rows = sorted(rows, key=lambda r: (r.template_title.lower(), r.template_id))
    start = max(int(offset), 0)
    end = start + max(int(limit), 1)
    page = rows[start:end]
    return ok(
        {
            "items": [_descriptor_to_v1(r).model_dump() for r in page],
            "limit": int(limit),
            "offset": int(offset),
            "returned": len(page),
            "total": len(rows),
        }
    )


@router.get("/templates/{template_id}")
async def api_templates_get(
    template_id: str,
    mode: str,
    version: Optional[int] = None,
) -> Dict[str, Any]:
    mode_or_fail = _normalize_mode_or_fail(mode)
    if not isinstance(mode_or_fail, str):
        return mode_or_fail
    mode_canonical = mode_or_fail
    try:
        row = _record_from_spec(mode_canonical, template_id, version=version)
    except Exception as e:
        return fail("TEMPLATE_NOT_FOUND", str(e), status=404)
    return ok({"template": row.model_dump()})


@router.get("/templates/{template_id}/versions")
async def api_templates_versions(template_id: str, mode: str) -> Dict[str, Any]:
    mode_or_fail = _normalize_mode_or_fail(mode)
    if not isinstance(mode_or_fail, str):
        return mode_or_fail
    mode_canonical = mode_or_fail
    versions = template_store.list_versions(template_id, mode_canonical)
    return ok({"template_id": template_id, "mode": mode_canonical, "versions": versions})


@router.post("/templates/draft")
async def api_templates_draft(payload: Dict[str, Any]) -> Dict[str, Any]:
    mode_or_fail = _normalize_mode_or_fail(str(payload.get("mode") or ""))
    if not isinstance(mode_or_fail, str):
        return mode_or_fail
    mode_canonical = mode_or_fail
    title = str(payload.get("template_title") or "").strip() or "Untitled Template"
    source_kind = str(payload.get("source_kind") or "text").strip().lower()
    raw_text = str(payload.get("raw_text") or payload.get("source_text") or "").strip()
    source_text = raw_text
    if source_kind == "pdf":
        try:
            bytes_b64 = str(payload.get("bytes_b64") or "").strip()
            pdf_bytes = base64.b64decode(bytes_b64) if bytes_b64 else b""
        except Exception:
            return fail("INVALID_PDF_PAYLOAD", "bytes_b64 must be valid base64-encoded PDF bytes.", status=400)
        source_text = extract_text_from_pdf(pdf_bytes)
    elif source_kind != "text":
        return fail("INVALID_SOURCE_KIND", "source_kind must be one of: text, pdf", status=400)

    if not source_text.strip():
        return fail("EMPTY_SOURCE_TEXT", "No source text available to draft template.", status=400)

    defaults_raw = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    base_draft = draft_from_source_text(mode_canonical, title, source_text)
    defaults = dict(base_draft.defaults)
    defaults["include_citations"] = bool(defaults_raw.get("include_citations", defaults["include_citations"]))
    defaults["show_empty_sections"] = bool(defaults_raw.get("show_empty_sections", defaults["show_empty_sections"]))
    draft = TemplateDraftV1(
        persisted=False,
        mode=mode_canonical,  # type: ignore[arg-type]
        template_title=base_draft.template_title,
        template_text=base_draft.template_text,
        defaults=defaults,
    )
    return ok({"draft": draft.model_dump()})


@router.post("/templates")
async def api_templates_create(payload: Dict[str, Any]) -> Dict[str, Any]:
    mode_or_fail = _normalize_mode_or_fail(str(payload.get("mode") or ""))
    if not isinstance(mode_or_fail, str):
        return mode_or_fail
    mode_canonical = mode_or_fail
    template_id = str(payload.get("template_id") or "").strip().lower()
    title = str(payload.get("template_title") or "").strip()
    text = str(payload.get("template_text") or "")
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    try:
        if template_id:
            rec = template_store.create_new_version(
                template_id=template_id,
                mode=mode_canonical,
                template_text=text,
                template_title=title or None,
                defaults=defaults,
            )
        else:
            rec = template_store.create_template(
                mode=mode_canonical,
                title=title,
                template_text=text,
                defaults=defaults,
            )
    except Exception as e:
        return fail("TEMPLATE_WRITE_FAILED", str(e), status=400)

    out = TemplateRecordV1(
        descriptor=TemplateDescriptorV1(
            template_id=rec.template_id,
            template_title=rec.template_title,
            template_version=str(rec.version),
            mode=rec.mode,  # type: ignore[arg-type]
            source="user",
        ),
        defaults=rec.defaults,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        template_text=rec.template_text,
    )
    return ok({"template": out.model_dump()})


@router.delete("/templates/{template_id}")
async def api_templates_delete(template_id: str, mode: str, confirm: bool = False):
    mode_or_fail = _normalize_mode_or_fail(mode)
    if not isinstance(mode_or_fail, str):
        return mode_or_fail
    mode_canonical = mode_or_fail
    if not confirm:
        return fail("CONFIRM_REQUIRED", "Set confirm=true to delete a template.", status=400)
    removed = template_store.delete_template(template_id, mode_canonical)
    if not removed:
        return fail("TEMPLATE_NOT_FOUND", "Template was not found.", status=404)
    return ok({"deleted": True, "template_id": template_id, "mode": mode_canonical})
