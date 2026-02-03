from __future__ import annotations

from fastapi.testclient import TestClient

from ashby.interfaces.web.app import create_app


def test_web_registry_exposes_modes_and_templates():
    app = create_app()
    c = TestClient(app)

    r = c.get("/api/registry")
    assert r.status_code == 200
    data = r.json()
    assert "modes" in data
    assert "templates_by_mode" in data
    assert "journal" in data["modes"]
    assert "meeting" in data["modes"]
    assert data["templates_by_mode"]["journal"] == ["default"]
    assert data["templates_by_mode"]["meeting"] == ["default"]


def test_index_has_mode_placeholder_and_no_default_selected():
    app = create_app()
    c = TestClient(app)

    r = c.get("/")
    assert r.status_code == 200
    html = r.text
    # placeholder must exist and be disabled so nothing is preselected
    assert '<option value="" selected disabled>Mode</option>' in html
