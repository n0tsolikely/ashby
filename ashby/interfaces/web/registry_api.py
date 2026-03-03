from __future__ import annotations

from typing import Any, Dict

from ashby.modules.meetings.mode_registry import allowed_modes, default_speakers_for_mode
from ashby.modules.meetings.retention_registry import allowed_retentions, default_retention
from ashby.modules.meetings.template_registry import template_descriptors_for_mode


def registry_payload() -> Dict[str, Any]:
    modes = allowed_modes()
    templates_by_mode: Dict[str, Any] = {}
    for mode in modes:
        templates_by_mode[mode] = [
            {
                "template_id": d.template_id,
                "template_title": d.template_title,
                "template_version": d.template_version,
                "mode": d.mode,
                "source": d.source,
            }
            for d in template_descriptors_for_mode(mode)
        ]
    defaults = {}
    for m in modes:
        try:
            defaults[m] = {"speakers": default_speakers_for_mode(m)}
        except Exception:
            defaults[m] = {"speakers": None}

    return {
        "modes": modes,
        "templates_by_mode": templates_by_mode,
        "retentions": allowed_retentions(),
        "default_retention": default_retention(),
        "defaults_by_mode": defaults,
    }
