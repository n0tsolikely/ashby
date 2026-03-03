from __future__ import annotations

from pathlib import Path

from tools.proofs.proof_d11_template_lifecycle import run_proof


def test_d11_template_lifecycle_proof(tmp_path: Path) -> None:
    result = run_proof(tmp_path / "runtime")
    assert result["ok"] is True
    assert result["template_id"]
    assert result["template_version"]
    assert result["zip_path"].endswith(".zip")
