from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from ashby.modules.meetings.init_root import init_stuart_root

AllowedMode = Literal["meeting", "journal"]
_ALLOWED_MODES = {"meeting", "journal"}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class TemplateDraft:
    mode: AllowedMode
    template_title: str
    template_text: str
    defaults: Dict[str, bool]


@dataclass(frozen=True)
class TemplateRecord:
    template_id: str
    template_title: str
    version: int
    mode: AllowedMode
    template_text: str
    defaults: Dict[str, bool]
    created_at: str
    updated_at: str
    source: str = "user"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _validate_mode(mode: str) -> AllowedMode:
    m = (mode or "").strip().lower()
    if m not in _ALLOWED_MODES:
        raise ValueError("mode must be one of: meeting, journal")
    return m  # type: ignore[return-value]


def _validate_version(version: int) -> int:
    if int(version) < 1:
        raise ValueError("version must be >= 1")
    return int(version)


def _validate_id(value: str, field_name: str = "template_id") -> str:
    v = (value or "").strip().lower()
    if not _ID_RE.match(v):
        raise ValueError(f"{field_name} must match {_ID_RE.pattern}")
    if ".." in v or "/" in v or "\\" in v:
        raise ValueError(f"{field_name} contains illegal path characters")
    return v


def _normalize_defaults(defaults: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    d = defaults or {}
    return {
        "include_citations": bool(d.get("include_citations", False)),
        "show_empty_sections": bool(d.get("show_empty_sections", False)),
    }


def _slugify_title(title: str) -> str:
    raw = (title or "").strip().lower()
    if not raw:
        raise ValueError("template_title is required")
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        raise ValueError("template_title must contain alphanumeric characters")
    return _validate_id(slug, field_name="template_id")


def template_root() -> Path:
    return init_stuart_root().templates / "user"


def template_dir(mode: str, template_id: str) -> Path:
    m = _validate_mode(mode)
    tid = _validate_id(template_id)
    return template_root() / m / tid


def template_version_dir(mode: str, template_id: str, version: int) -> Path:
    v = _validate_version(version)
    return template_dir(mode, template_id) / f"v{v}"


def _list_existing_versions(mode: str, template_id: str) -> List[int]:
    root = template_dir(mode, template_id)
    if not root.exists():
        return []
    out: List[int] = []
    for child in root.iterdir():
        name = child.name
        if child.is_dir() and name.startswith("v") and name[1:].isdigit():
            val = int(name[1:])
            if val >= 1:
                out.append(val)
    return sorted(out)


def _metadata_path(mode: str, template_id: str, version: int) -> Path:
    return template_version_dir(mode, template_id, version) / "metadata.json"


def _template_path(mode: str, template_id: str, version: int) -> Path:
    return template_version_dir(mode, template_id, version) / "template.md"


def _write_record(record: TemplateRecord) -> None:
    vdir = template_version_dir(record.mode, record.template_id, record.version)
    vdir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "template_id": record.template_id,
        "template_title": record.template_title,
        "version": record.version,
        "mode": record.mode,
        "defaults": record.defaults,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "source": "user",
    }
    _metadata_path(record.mode, record.template_id, record.version).write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _template_path(record.mode, record.template_id, record.version).write_text(
        record.template_text,
        encoding="utf-8",
    )


def create_template(mode: str, title: str, template_text: str, defaults: Optional[Dict[str, Any]] = None) -> TemplateRecord:
    m = _validate_mode(mode)
    template_root().mkdir(parents=True, exist_ok=True)
    base_id = _slugify_title(title)
    tid = base_id
    suffix = 2
    while template_dir(m, tid).exists():
        tid = f"{base_id}_{suffix}"
        suffix += 1
    now = _now_iso()
    record = TemplateRecord(
        template_id=tid,
        template_title=title.strip(),
        version=1,
        mode=m,
        template_text=template_text,
        defaults=_normalize_defaults(defaults),
        created_at=now,
        updated_at=now,
    )
    _write_record(record)
    return record


def create_new_version(
    template_id: str,
    mode: str,
    template_text: str,
    template_title: Optional[str] = None,
    defaults: Optional[Dict[str, Any]] = None,
) -> TemplateRecord:
    m = _validate_mode(mode)
    tid = _validate_id(template_id)
    versions = _list_existing_versions(m, tid)
    if not versions:
        raise FileNotFoundError(f"template not found: mode={m} template_id={tid}")
    latest = load_template(tid, m, version=max(versions))
    next_version = max(versions) + 1
    now = _now_iso()
    record = TemplateRecord(
        template_id=tid,
        template_title=(template_title.strip() if template_title is not None else latest.template_title),
        version=next_version,
        mode=m,
        template_text=template_text,
        defaults=_normalize_defaults(defaults if defaults is not None else latest.defaults),
        created_at=latest.created_at,
        updated_at=now,
    )
    _write_record(record)
    return record


def list_versions(template_id: str, mode: str) -> List[int]:
    return _list_existing_versions(mode, template_id)


def load_template(template_id: str, mode: str, version: int) -> TemplateRecord:
    m = _validate_mode(mode)
    tid = _validate_id(template_id)
    v = _validate_version(version)
    meta_path = _metadata_path(m, tid, v)
    text_path = _template_path(m, tid, v)
    if not meta_path.exists() or not text_path.exists():
        raise FileNotFoundError(f"missing template version: mode={m} template_id={tid} version={v}")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    return TemplateRecord(
        template_id=str(metadata.get("template_id") or tid),
        template_title=str(metadata.get("template_title") or ""),
        version=int(metadata.get("version") or v),
        mode=_validate_mode(str(metadata.get("mode") or m)),
        template_text=text_path.read_text(encoding="utf-8"),
        defaults=_normalize_defaults(metadata.get("defaults") if isinstance(metadata, dict) else None),
        created_at=str(metadata.get("created_at") or ""),
        updated_at=str(metadata.get("updated_at") or ""),
    )


def list_templates(mode: str) -> List[TemplateRecord]:
    m = _validate_mode(mode)
    root = template_root() / m
    if not root.exists():
        return []
    rows: List[TemplateRecord] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        tid = _validate_id(child.name)
        versions = _list_existing_versions(m, tid)
        if not versions:
            continue
        rows.append(load_template(tid, m, max(versions)))
    return rows


def delete_template(template_id: str, mode: str) -> bool:
    tdir = template_dir(mode, template_id)
    if not tdir.exists():
        return False
    shutil.rmtree(tdir)
    return True

