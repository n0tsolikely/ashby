#!/usr/bin/env python3
from __future__ import annotations

"""
Proof: Dungeon 11 template lifecycle (deterministic local run).

How to run:
  PYTHONPATH=/home/notsolikely/Ashby_Engine python tools/proofs/proof_d11_template_lifecycle.py --temp
  PYTHONPATH=/home/notsolikely/Ashby_Engine python tools/proofs/proof_d11_template_lifecycle.py --stuart-root /tmp/stuart_runtime

PASS looks like:
  - Exit code 0
  - Printed JSON includes ok=true and a dev export zip path

Outputs:
  - Runtime artifacts under STUART_ROOT
  - Dev export zip under STUART_ROOT/exports
"""

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Any
import zipfile

import httpx

from ashby.interfaces.web.app import create_app
from ashby.modules.meetings.export.bundle import export_session_bundle
from ashby.modules.meetings.formalize.minutes_json import formalize_meeting_to_minutes_json


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_proof(stuart_root: Path) -> Dict[str, Any]:
    os.environ["STUART_ROOT"] = str(stuart_root)
    os.environ["ASHBY_EXECUTION_PROFILE"] = "LOCAL_ONLY"
    os.environ.pop("ASHBY_MEETINGS_LLM_ENABLED", None)

    app = create_app()

    async def _create_template_and_check_registry() -> tuple[str, str, str]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1) Create user template via API
            created = await client.post(
                "/api/templates",
                json={
                    "mode": "meeting",
                    "template_title": "Proof Template",
                    "template_text": "## Overview\n\n## Decisions\n\n## Action Items\n",
                    "defaults": {"include_citations": False, "show_empty_sections": False},
                },
            )
            created.raise_for_status()
            payload = created.json()
            template_id = payload["template"]["descriptor"]["template_id"]
            template_version = payload["template"]["descriptor"]["template_version"]
            template_title = payload["template"]["descriptor"]["template_title"]

            # 2) Verify registry exposes it
            reg = await client.get("/api/registry")
            reg.raise_for_status()
            rows = reg.json().get("templates_by_mode", {}).get("meeting", [])
            assert any(r.get("template_id") == template_id for r in rows)
            return template_id, template_version, template_title

    template_id, template_version, template_title = asyncio.run(_create_template_and_check_registry())

    # 3) Build minimal session/run transcript substrate
    sid = "ses_proof_d11"
    rid = "run_proof_d11"
    run_dir = stuart_root / "runs" / rid
    _write_json(stuart_root / "sessions" / sid / "session.json", {"session_id": sid, "created_ts": 1, "mode": "meeting"})
    _write_json(stuart_root / "sessions" / sid / "session_state.json", {"session_id": sid, "active_transcript_version_id": "trv_proof"})
    _write_json(
        run_dir / "run.json",
        {
            "run_id": rid,
            "session_id": sid,
            "created_ts": 1,
            "primary_outputs": {"mode": "meeting", "json": {"path": "artifacts/minutes.json"}},
            "plan": {"steps": [{"kind": "formalize", "params": {"mode": "meeting", "template_id": template_id}}]},
        },
    )
    (run_dir / "events.jsonl").write_text("{}\n", encoding="utf-8")
    _write_json(
        run_dir / "artifacts" / "aligned_transcript.json",
        {
            "version": 1,
            "session_id": sid,
            "run_id": rid,
            "segments": [{"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "Proof run transcript."}],
            "engine": "proof",
        },
    )

    # 4) Formalize using user template and fixed version
    formalize_meeting_to_minutes_json(
        run_dir,
        template_id=template_id,
        template_version=template_version,
        retention="MED",
    )
    out = json.loads((run_dir / "artifacts" / "minutes.json").read_text(encoding="utf-8"))
    assert out["template_id"] == template_id
    assert str(out["template_version"]) == str(template_version)
    assert out["template_title"] == template_title

    # 5) Dev export contains exact template internals
    dev = export_session_bundle(sid, export_type="dev_bundle")
    with zipfile.ZipFile(dev.zip_path) as zf:
        names = set(zf.namelist())
        assert f"dev/templates/{rid}/{template_id}/v{template_version}/metadata.json" in names
        assert f"dev/templates/{rid}/{template_id}/v{template_version}/template.md" in names

    return {
        "ok": True,
        "session_id": sid,
        "run_id": rid,
        "template_id": template_id,
        "template_version": template_version,
        "zip_path": dev.zip_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stuart-root", type=str, default="")
    parser.add_argument("--temp", action="store_true")
    args = parser.parse_args()

    if args.temp or not args.stuart_root:
        with tempfile.TemporaryDirectory(prefix="d11_proof_") as td:
            result = run_proof(Path(td))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

    result = run_proof(Path(args.stuart_root))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
