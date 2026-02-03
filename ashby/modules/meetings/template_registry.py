from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

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


def validate_template(mode: str, template_id: str) -> TemplateValidation:
    mv = validate_mode(mode)
    allowed: List[str] = []
    if mv.ok and mv.canonical is not None:
        allowed = allowed_templates_for_mode(mv.canonical)

    tid = (template_id or "").strip().lower()
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

    if tid in allowed:
        return TemplateValidation(
            ok=True,
            mode_raw=mode,
            mode_canonical=mv.canonical,
            template_raw=template_id,
            template_id=tid,
            allowed_templates=allowed,
        )

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


def system_template_path(mode: str, template_id: str) -> Path:
    tv = validate_template(mode, template_id)
    if not tv.ok or tv.mode_canonical is None or tv.template_id is None:
        raise ValueError(tv.message or "Invalid mode/template.")
    return _SYSTEM_DIR / tv.mode_canonical / f"{tv.template_id}.md"


def load_system_template_text(mode: str, template_id: str) -> str:
    path = system_template_path(mode, template_id)
    return path.read_text(encoding="utf-8")


def allowed_templates() -> Dict[str, List[str]]:
    """
    Global template availability map.
    Returns a copy so callers can't mutate internal tables.
    """
    return {k: list(v) for k, v in _V1_TEMPLATES_BY_MODE.items()}
