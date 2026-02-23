from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ashby.modules.meetings.cli_stuart import cmd_upload, cmd_run, cmd_status


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _gen_wav(path: Path) -> None:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not installed")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.2", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def test_cli_upload_run_status(tmp_path: Path, monkeypatch):
    root = tmp_path / "stuart_runtime"
    monkeypatch.setenv("STUART_ROOT", str(root))

    f = tmp_path / "a.wav"
    _gen_wav(f)

    out_up = cmd_upload(NS(path=str(f), kind="audio", mode="meeting", title="t", session_id=None))
    assert out_up["ok"] is True
    ses = out_up["session_id"]

    out_run = cmd_run(NS(session_id=ses, mode="meeting", template="default", contribution_id="", yes=True))
    assert out_run["ok"] is True
    run_id = out_run["run_id"]
    assert out_run["state"]["status"] == "succeeded"

    out_st = cmd_status(NS(run_id=run_id))
    assert out_st["ok"] is True
    assert out_st["state"]["run_id"] == run_id

    md = Path(root) / "runs" / run_id / "artifacts" / "minutes.md"
    assert md.exists()
    assert not (Path(root) / "runs" / run_id / "artifacts" / "formalized.md").exists()
