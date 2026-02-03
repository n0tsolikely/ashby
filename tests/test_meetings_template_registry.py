from ashby.modules.meetings.template_registry import (
    allowed_templates_for_mode,
    validate_template,
    system_template_path,
    load_system_template_text,
)


def test_v1_templates_default_only():
    assert allowed_templates_for_mode("journal") == ["default"]
    assert allowed_templates_for_mode("meeting") == ["default"]


def test_unknown_template_rejected():
    v = validate_template("journal", "fancy")
    assert v.ok is False
    assert v.template_id is None
    assert "Allowed" in (v.message or "")


def test_system_template_paths_exist_and_load():
    p = system_template_path("journal", "default")
    assert p.name == "default.md"
    txt = load_system_template_text("journal", "default")
    assert len(txt.strip()) > 0


def test_global_templates_available():
    from ashby.modules.meetings.template_registry import allowed_templates
    m = allowed_templates()
    assert m["journal"] == ["default"]
    assert m["meeting"] == ["default"]
