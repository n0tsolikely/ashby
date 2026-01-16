from __future__ import annotations

from ashby.core.truth.evidence import EvidenceBundle
from ashby.core.truth.judge import TruthGateJudge
from ashby.core.truth.policy import ForbiddenPhrasesPolicy


def test_truth_gate_spine_forbidden_phrase_rewrite_and_pass_through() -> None:
    evidence = EvidenceBundle.empty()
    judge = TruthGateJudge()

    # Use custom phrases so this test is deterministic and not tied to whatever the legacy list is today.
    policy = ForbiddenPhrasesPolicy(phrases=["unicorn"], reject="REJECTED")

    bad = "I definitely saw a unicorn yesterday."
    d = judge.evaluate(bad, evidence, policy)

    assert d.allowed is False
    assert d.blocked is True
    assert d.rewritten == "REJECTED"
    assert len(d.violations) >= 1
    assert d.violations[0].code == "FORBIDDEN_PHRASE"

    out = judge.apply(bad, evidence, policy)
    assert out == "REJECTED"

    good = "hello there"
    d2 = judge.evaluate(good, evidence, policy)

    assert d2.allowed is True
    assert d2.blocked is False
    assert d2.rewritten is None
    assert d2.violations == []

    out2 = judge.apply(good, evidence, policy)
    assert out2 == good
