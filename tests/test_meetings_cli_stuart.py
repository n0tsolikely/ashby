from pathlib import Path

from ashby.modules.meetings.cli_stuart import cmd_upload, cmd_run, cmd_status


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_cli_upload_run_status(tmp_path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    # create a fake audio file
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFFxxxxWAVEfake")

    out_up = cmd_upload(NS(path=str(f), kind="audio", mode="meeting", title="t", session_id=None))
    assert out_up["ok"] is True
    ses = out_up["session_id"]

    out_run = cmd_run(NS(session_id=ses, mode="meeting", template="default"))
    assert out_run["ok"] is True
    run_id = out_run["run_id"]
    assert out_run["state"]["status"] == "succeeded"

    out_st = cmd_status(NS(run_id=run_id))
    assert out_st["ok"] is True
    assert out_st["state"]["run_id"] == run_id

    # sanity: formalized.md exists
    md = Path(root) / "runs" / run_id / "artifacts" / "formalized.md"
    assert md.exists()
