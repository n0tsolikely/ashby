from ashby.modules.meetings.template_registry import (
    allowed_templates_for_mode,
    validate_template,
    system_template_path,
    load_system_template_text,
    load_template_spec,
    get_template_defaults,
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
    assert "Citation Rules" in tj
    assert "DO NOT invent" in tj

    assert "segment_id" in tm
    assert "Citation Rules" in tm
    assert "DO NOT invent" in tm


def test_global_templates_available():
    from ashby.modules.meetings.template_registry import allowed_templates
    m = allowed_templates()
    assert m["journal"] == ["default"]
    assert m["meeting"] == ["default"]


def test_load_template_spec_parses_front_matter_defaults_and_sections():
    ms = load_template_spec("meeting", "default")
    js = load_template_spec("journal", "default")

    assert ms.template_version == "2"
    assert js.template_version == "2"

    assert ms.defaults["include_citations"] is False
    assert ms.defaults["show_empty_sections"] is False
    assert js.defaults["include_citations"] is False
    assert js.defaults["show_empty_sections"] is False

    assert len(ms.sections) > 0
    assert len(js.sections) > 0
    assert any(s.heading == "Decisions" for s in ms.sections)
    assert any(s.heading == "Narrative" for s in js.sections)


def test_get_template_defaults_helper():
    d = get_template_defaults("meeting", "default")
    assert d == {"include_citations": False, "show_empty_sections": False}


def test_validate_template_rejects_malformed_front_matter(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ashby.modules.meetings.template_registry._SYSTEM_DIR",
        tmp_path / "system",
    )
    bad = tmp_path / "system" / "meeting"
    bad.mkdir(parents=True, exist_ok=True)
    # starts front matter but never closes it
    (bad / "default.md").write_text("---\ntemplate_version: 2\n", encoding="utf-8")
    v = validate_template("meeting", "default")
    assert v.ok is False
    assert "Template parse failed" in (v.message or "")
