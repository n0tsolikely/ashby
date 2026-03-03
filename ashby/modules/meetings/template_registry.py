from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ashby.modules.meetings.mode_registry import validate_mode

# v1 ships exactly ONE template per mode: "default"
_V1_TEMPLATES_BY_MODE: Dict[str, List[str]] = {
    "journal": ["default"],
    "meeting": ["default"],
}

_THIS_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _THIS_DIR / "templates"
_SYSTEM_DIR = _TEMPLATES_DIR / "system"
_USER_DIR = _TEMPLATES_DIR / "user"


@dataclass(frozen=True)
class TemplateValidation:
    ok: bool
    mode_raw: str
    mode_canonical: Optional[str]
    template_raw: str
    template_id: Optional[str]
    allowed_templates: List[str]
    message: Optional[str] = None


@dataclass(frozen=True)
class TemplateSection:
    section_id: str
    heading: str
    level: int


@dataclass(frozen=True)
class TemplateSpec:
    mode: str
    template_id: str
    template_version: str
    defaults: Dict[str, Any]
    sections: List[TemplateSection]
    raw_text: str
    body_text: str
    path: Path


def templates_dir() -> Path:
    return _TEMPLATES_DIR


def system_templates_dir() -> Path:
    return _SYSTEM_DIR


def user_templates_dir() -> Path:
    return _USER_DIR


def allowed_templates_for_mode(mode: str) -> List[str]:
    mv = validate_mode(mode)
    if not mv.ok or mv.canonical is None:
        return []
    return list(_V1_TEMPLATES_BY_MODE.get(mv.canonical, []))


def _parse_scalar(value: str) -> Any:
    v = value.strip()
    lo = v.lower()
    if lo in {"true", "false"}:
        return lo == "true"
    if lo in {"null", "none"}:
        return None
    return v


def _parse_front_matter(block: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    current_parent: Optional[str] = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  ") and current_parent:
            sub = line.strip()
            if ":" not in sub:
                raise ValueError(f"invalid front matter line: {raw}")
            k, v = sub.split(":", 1)
            parent = data.get(current_parent)
            if not isinstance(parent, dict):
                parent = {}
                data[current_parent] = parent
            parent[k.strip()] = _parse_scalar(v)
            continue
        if ":" not in line:
            raise ValueError(f"invalid front matter line: {raw}")
        k, v = line.split(":", 1)
        key = k.strip()
        value = v.strip()
        if not key:
            raise ValueError(f"invalid front matter key: {raw}")
        if value == "":
            data[key] = {}
            current_parent = key
        else:
            data[key] = _parse_scalar(value)
            current_parent = None
    return data


def _split_front_matter(text: str) -> tuple[Dict[str, Any], str]:
    # YAML-like markdown front matter:
    # ---
    # key: value
    # defaults:
    #   include_citations: false
    # ---
    if not text.startswith("---\n"):
        return ({}, text)
    end_idx = text.find("\n---\n", 4)
    if end_idx < 0:
        raise ValueError("template front matter starts with '---' but closing '---' is missing")
    front = text[4:end_idx]
    body = text[end_idx + 5 :]
    return (_parse_front_matter(front), body)


def _parse_sections(body_text: str) -> List[TemplateSection]:
    out: List[TemplateSection] = []
    for line in body_text.splitlines():
        s = line.strip()
        if not s.startswith("#"):
            continue
        level = len(s) - len(s.lstrip("#"))
        if level < 2 or level > 3:
            continue
        heading = s[level:].strip()
        if not heading:
            continue
        section_id = heading.lower()
        section_id = "".join(ch if ch.isalnum() else "_" for ch in section_id)
        section_id = "_".join([p for p in section_id.split("_") if p]) or "section"
        out.append(TemplateSection(section_id=section_id, heading=heading, level=level))
    return out


def _template_identity(mode: str, template_id: str) -> tuple[str, str, List[str]]:
    mv = validate_mode(mode)
    if not mv.ok or mv.canonical is None:
        raise ValueError(mv.message or "Invalid mode.")
    tid = (template_id or "").strip().lower()
    allowed = allowed_templates_for_mode(mv.canonical)
    if tid not in allowed:
        raise ValueError(f"Unknown template '{template_id}' for mode '{mv.canonical}'. Allowed: {', '.join(allowed)}.")
    return mv.canonical, tid, allowed


def validate_template(mode: str, template_id: str) -> TemplateValidation:
    mv = validate_mode(mode)
    allowed: List[str] = allowed_templates_for_mode(mode)
    if not mv.ok or mv.canonical is None:
        return TemplateValidation(
            ok=False,
            mode_raw=mode,
            mode_canonical=None,
            template_raw=template_id,
            template_id=None,
            allowed_templates=allowed,
            message=mv.message,
        )

    tid = (template_id or "").strip().lower()
    if tid not in allowed:
        msg = f"Unknown template '{template_id}' for mode '{mv.canonical}'. Allowed: {', '.join(allowed)}."
        return TemplateValidation(
            ok=False,
            mode_raw=mode,
            mode_canonical=mv.canonical,
            template_raw=template_id,
            template_id=None,
            allowed_templates=allowed,
            message=msg,
        )

    # QUEST_160 rail: malformed front matter must fail validation with a clear error.
    try:
        _ = load_template_spec(mv.canonical, tid)
    except Exception as e:
        return TemplateValidation(
            ok=False,
            mode_raw=mode,
            mode_canonical=mv.canonical,
            template_raw=template_id,
            template_id=None,
            allowed_templates=allowed,
            message=f"Template parse failed: {type(e).__name__}: {e}",
        )

    return TemplateValidation(
        ok=True,
        mode_raw=mode,
        mode_canonical=mv.canonical,
        template_raw=template_id,
        template_id=tid,
        allowed_templates=allowed,
    )


def system_template_path(mode: str, template_id: str) -> Path:
    mode_canonical, tid, _ = _template_identity(mode, template_id)
    return _SYSTEM_DIR / mode_canonical / f"{tid}.md"


def load_system_template_text(mode: str, template_id: str) -> str:
    path = system_template_path(mode, template_id)
    return path.read_text(encoding="utf-8")


def load_template_spec(mode: str, template_id: str, user_id: Optional[str] = None) -> TemplateSpec:
    # user_id retained for forward compatibility with user template storage.
    del user_id
    path = system_template_path(mode, template_id)
    raw_text = path.read_text(encoding="utf-8")
    front, body_text = _split_front_matter(raw_text)
    template_version = str(front.get("template_version") or "1").strip() or "1"
    defaults = front.get("defaults")
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise ValueError("template front matter defaults must be an object")
    include_citations = defaults.get("include_citations")
    show_empty_sections = defaults.get("show_empty_sections")
    normalized_defaults = {
        "include_citations": bool(include_citations) if isinstance(include_citations, bool) else False,
        "show_empty_sections": bool(show_empty_sections) if isinstance(show_empty_sections, bool) else False,
    }
    sections = _parse_sections(body_text)
    if not sections:
        raise ValueError("template body must include markdown headings for section parsing")
    mode_canonical, tid, _ = _template_identity(mode, template_id)
    return TemplateSpec(
        mode=mode_canonical,
        template_id=tid,
        template_version=template_version,
        defaults=normalized_defaults,
        sections=sections,
        raw_text=raw_text,
        body_text=body_text,
        path=path,
    )


def get_template_defaults(mode: str, template_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    spec = load_template_spec(mode, template_id, user_id=user_id)
    return dict(spec.defaults)


def allowed_templates() -> Dict[str, List[str]]:
    """
    Global template availability map.
    Returns a copy so callers can't mutate internal tables.
    """
    return {k: list(v) for k, v in _V1_TEMPLATES_BY_MODE.items()}
