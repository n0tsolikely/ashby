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
    pj = system_template_path("journal", "default")
    pm = system_template_path("meeting", "default")
    assert pj.name == "default.md"
    assert pm.name == "default.md"

    tj = load_system_template_text("journal", "default")
    tm = load_system_template_text("meeting", "default")

    assert len(tj.strip()) > 0
    assert len(tm.strip()) > 0

    # QUEST_043: templates must require evidence discipline + citations by segment_id
    assert "segment_id" in tj
    assert "CITATION FORMAT" in tj
    assert "DO NOT invent" in tj

    assert "segment_id" in tm
    assert "CITATION FORMAT" in tm
    assert "DO NOT invent" in tm


def test_global_templates_available():
    from ashby.modules.meetings.template_registry import allowed_templates
    m = allowed_templates()
    assert m["journal"] == ["default"]
    assert m["meeting"] == ["default"]
