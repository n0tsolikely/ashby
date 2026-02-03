from pathlib import Path
import time

from fastapi.testclient import TestClient

from ashby.interfaces.web.app import create_app


def test_web_upload_and_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUART_ROOT", str(tmp_path / "stuart_runtime"))

    app = create_app()
    c = TestClient(app)

    r = c.post("/api/sessions", json={"mode": "journal", "title": "web test"})
    sid = r.json()["session_id"]

    fake = b"RIFFxxxxWAVEfmt " + b"0" * 64
    files = {"file": ("test.wav", fake, "audio/wav")}
    r2 = c.post(f"/api/upload?session_id={sid}", files=files)
    j = r2.json()
    assert j["ok"] is True
    att = j["attachment"]

    r3 = c.post("/api/message", json={
        "session_id": sid,
        "text": "formalize this",
        "ui": {"mode": "journal", "template": None, "speakers": None},
        "attachments": [att],
    })
    out = r3.json()["result"]
    assert out["needs_clarification"] is False

    r4 = c.post("/api/run", json={"session_id": sid, "ui": {"mode": "journal", "template": "default", "speakers": None}})
    j4 = r4.json()
    assert j4["ok"] is True
    run_id = j4["run_id"]

    # poll status
    for _ in range(50):
        st = c.get(f"/api/runs/{run_id}").json()
        status = (st["state"] or {}).get("status")
        if status in ("succeeded", "failed"):
            break
        time.sleep(0.05)

    st = c.get(f"/api/runs/{run_id}").json()
    assert (st["state"] or {}).get("status") == "succeeded"
    arts = st.get("artifacts") or []
    assert len(arts) >= 1
