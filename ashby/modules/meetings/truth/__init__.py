"""Meetings truth-gate integration.

This package provides:
- Evidence bundle builders for the Meetings module.
- MeetingsTruthPolicy: module policy for platform TruthGateJudge.
- gate_formalized_output: wiring helper used by the meetings pipeline.

Design goal (Codex): keep platform truth spine generic, keep module truth rules local.
"""

from .evidence_bundle import build_meetings_evidence_bundle
from .meetings_truth_policy import MeetingsTruthPolicy
from .gate import gate_formalized_output

__all__ = [
    "build_meetings_evidence_bundle",
    "MeetingsTruthPolicy",
    "gate_formalized_output",
]
