from __future__ import annotations

from ashby.modules.meetings.template_registry import (
    allowed_templates_for_mode,
    load_template_spec,
    validate_template,
)
from ashby.modules.meetings.templates.store import create_template


def test_allowed_templates_merges_system_and_user(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "runtime"))
    rec = create_template(
        mode="meeting",
        title="Ops Template",
        template_text="## Overview\n\n## Actions\n",
    )

    allowed = allowed_templates_for_mode("meeting")
    assert "default" in allowed
    assert rec.template_id in allowed


def test_load_template_spec_user_version_and_title(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "runtime"))
    rec = create_template(
        mode="meeting",
        title="Delivery Log",
        template_text="## Update\n\n## Risks\n",
        defaults={"include_citations": True, "show_empty_sections": True},
    )

    spec = load_template_spec("meeting", rec.template_id, version=1)
    assert spec.template_id == rec.template_id
    assert spec.template_title == "Delivery Log"
    assert spec.template_version == "1"
    assert spec.defaults["include_citations"] is True


def test_validate_template_rejects_unknown_template_id() -> None:
    v = validate_template("meeting", "not_real_template")
    assert v.ok is False
    assert "Unknown template" in (v.message or "")
