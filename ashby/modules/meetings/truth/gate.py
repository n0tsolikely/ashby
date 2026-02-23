from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Tuple

from ashby.core.truth.judge import TruthGateDecision, TruthGateJudge

from ashby.modules.meetings.hashing import sha256_file
from ashby.modules.meetings.schemas.artifacts_v1 import dump_json

from .evidence_bundle import build_meetings_evidence_bundle
from .meetings_truth_policy import MeetingsTruthPolicy


def _decision_to_dict(d: TruthGateDecision) -> Dict[str, Any]:
    return {
        "allowed": d.allowed,
        "blocked": d.blocked,
        "rewritten": d.rewritten,
        "violations": [
            {
                "code": v.code,
                "message": v.message,
                "severity": v.severity,
                "evidence_required": v.evidence_required,
                "meta": v.meta,
            }
            for v in d.violations
        ],
    }


def gate_formalized_output(
    *,
    run_dir: Path,
    session_id: str,
    run_id: str,
    mode: str,
) -> Tuple[TruthGateDecision, Dict[str, Any]]:
    """Run the platform truth gate against the meetings formalized JSON.

    Wiring contract:
    - Must run AFTER minutes.json/journal.json exists
    - Must run BEFORE MD/PDF outputs are produced
    - Must write a machine-readable report artifact (write-once)

    Returns (decision, artifact_dict_for_manifest).
    """
    artifacts = run_dir / "artifacts"

    draft_path = artifacts / ("minutes.json" if mode == "meeting" else "journal.json")
    if not draft_path.exists():
        raise FileNotFoundError(f"Missing draft for truth gate: {draft_path}")

    draft = draft_path.read_text(encoding="utf-8")

    evidence = build_meetings_evidence_bundle(
        session_id=session_id,
        run_id=run_id,
        run_dir=run_dir,
        mode=mode,
    )

    policy = MeetingsTruthPolicy()
    judge = TruthGateJudge()
    decision = judge.evaluate(draft, evidence, policy)

    report_path = artifacts / "truth_gate_report.json"
    report_payload: Dict[str, Any] = {
        "version": 1,
        "created_ts": time.time(),
        "session_id": session_id,
        "run_id": run_id,
        "mode": mode,
        "policy_id": getattr(policy, "policy_id", ""),
        "draft_file": draft_path.name,
        "decision": _decision_to_dict(decision),
    }

    dump_json(report_path, report_payload, write_once=True)

    art = {
        "kind": "truth_gate_report",
        "path": str(report_path),
        "sha256": sha256_file(report_path),
        "mime": "application/json",
        "created_ts": report_payload["created_ts"],
        "policy_id": report_payload["policy_id"],
        "allowed": decision.allowed,
        "blocked": decision.blocked,
    }

    return decision, art
