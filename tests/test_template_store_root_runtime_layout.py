from __future__ import annotations

from pathlib import Path

from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.template_registry import user_templates_dir


def test_init_stuart_root_creates_runtime_templates_dir(monkeypatch, tmp_path) -> None:
    runtime_root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(runtime_root))

    layout = init_stuart_root()

    assert layout.templates == runtime_root.resolve() / "templates"
    assert layout.templates.exists()
    assert layout.templates.is_dir()


def test_user_templates_dir_resolves_under_runtime_templates(monkeypatch, tmp_path) -> None:
    runtime_root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(runtime_root))

    resolved = user_templates_dir()

    expected_prefix = (runtime_root.resolve() / "templates")
    assert resolved == expected_prefix / "user"
    assert str(resolved).startswith(str(expected_prefix))
    assert "Ashby_Engine/ashby/modules/meetings/templates" not in str(resolved)

