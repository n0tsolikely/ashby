from __future__ import annotations

from ashby.interfaces.web.app import create_app


def test_dungeon2_minimum_routes_exist():
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}

    required = {
        "/api/sessions",
        "/api/sessions/{session_id}",
        "/api/sessions/{session_id}/runs",
        "/api/sessions/{session_id}/transcripts",
        "/api/sessions/{session_id}/transcripts/active",
        "/api/transcripts/{transcript_version_id}",
        "/api/sessions/{session_id}/formalizations",
        "/api/sessions/{session_id}/export",
        "/api/exports/{filename}",
        "/api/run",
        "/api/runs/{run_id}",
        "/api/chat",
        "/api/chat/global",
    }
    missing = sorted(required - paths)
    assert not missing, f"Missing required Dungeon 2 routes: {missing}"


def test_route_alias_download_and_legacy_message_remain():
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/download/{run_id}/{filename}" in paths
    assert "/api/message" in paths
