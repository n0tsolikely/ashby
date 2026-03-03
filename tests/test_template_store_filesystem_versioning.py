from __future__ import annotations

from ashby.modules.meetings.templates.store import (
    create_new_version,
    create_template,
    delete_template,
    list_templates,
    load_template,
    template_root,
    template_version_dir,
)


def test_create_template_writes_v1_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "runtime"))

    rec = create_template(
        mode="meeting",
        title="Exec Minutes",
        template_text="## Agenda\n\n## Decisions\n",
        defaults={"include_citations": True, "show_empty_sections": False},
    )

    v1 = template_version_dir("meeting", rec.template_id, 1)
    assert rec.version == 1
    assert v1.exists()
    assert (v1 / "metadata.json").exists()
    assert (v1 / "template.md").read_text(encoding="utf-8").startswith("## Agenda")


def test_create_new_version_keeps_v1_immutable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "runtime"))
    rec1 = create_template(
        mode="meeting",
        title="Status Template",
        template_text="## Status v1\n",
        defaults={"include_citations": False, "show_empty_sections": False},
    )

    rec2 = create_new_version(
        template_id=rec1.template_id,
        mode="meeting",
        template_text="## Status v2\n",
        template_title="Status Template Updated",
    )

    assert rec2.version == 2
    assert (template_version_dir("meeting", rec1.template_id, 1) / "template.md").read_text(encoding="utf-8") == "## Status v1\n"
    assert (template_version_dir("meeting", rec1.template_id, 2) / "template.md").read_text(encoding="utf-8") == "## Status v2\n"


def test_list_templates_returns_latest_and_load_specific_version(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "runtime"))
    rec1 = create_template(mode="journal", title="Journal Alpha", template_text="## Day 1\n")
    _ = create_new_version(template_id=rec1.template_id, mode="journal", template_text="## Day 2\n")

    listed = list_templates("journal")
    assert len(listed) == 1
    assert listed[0].version == 2
    assert listed[0].template_id == rec1.template_id

    v1 = load_template(rec1.template_id, "journal", 1)
    assert v1.version == 1
    assert v1.template_text == "## Day 1\n"


def test_delete_template_removes_tree(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "runtime"))
    rec = create_template(mode="meeting", title="To Delete", template_text="## X\n")
    root = template_root() / "meeting" / rec.template_id
    assert root.exists()

    removed = delete_template(rec.template_id, "meeting")
    assert removed is True
    assert not root.exists()
