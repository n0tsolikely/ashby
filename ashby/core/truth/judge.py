from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import EvidenceBundle, TruthViolation
from .policy import TruthPolicy


@dataclass(kw_only=True)
class TruthGateDecision:
    allowed: bool
    blocked: bool
    rewritten: str | None
    violations: list[TruthViolation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise TypeError("allowed must be a bool")
        if not isinstance(self.blocked, bool):
            raise TypeError("blocked must be a bool")
        if self.rewritten is not None and not isinstance(self.rewritten, str):
            raise TypeError("rewritten must be a str or None")
        if not isinstance(self.violations, list):
            raise TypeError("violations must be a list[TruthViolation]")
        for v in self.violations:
            if not isinstance(v, TruthViolation):
                raise TypeError("violations must be a list[TruthViolation]")

        # Contract rule:
        # - allowed == True implies blocked == False.
        if self.allowed and self.blocked:
            raise ValueError("allowed=True implies blocked=False")

        # Keep decision states consistent (Batch 0 spine)
        if self.blocked and self.allowed:
            raise ValueError("blocked=True cannot have allowed=True")
        if (not self.allowed) and (not self.blocked):
            raise ValueError("invalid TruthGateDecision: neither allowed nor blocked")


class TruthGateJudge:
    """
    Platform judge that applies a TruthPolicy to a draft, given evidence.
    Deterministic + side-effect-free.
    """

    DEFAULT_BLOCK_MESSAGE = "Blocked by truth policy."

    def evaluate(self, draft: str, evidence: EvidenceBundle, policy: TruthPolicy) -> TruthGateDecision:
        if not isinstance(draft, str):
            raise TypeError("draft must be a str")
        if not isinstance(evidence, EvidenceBundle):
            raise TypeError("evidence must be an EvidenceBundle")

        violations = policy.validate(draft, evidence)
        if not isinstance(violations, list):
            raise TypeError("policy.validate must return list[TruthViolation]")

        for v in violations:
            if not isinstance(v, TruthViolation):
                raise TypeError("policy.validate must return list[TruthViolation]")

        blocked = any(v.severity == "block" for v in violations)

        rewritten = policy.rewrite(draft, evidence, violations)
        if rewritten is not None and not isinstance(rewritten, str):
            raise TypeError("policy.rewrite must return str or None")

        allowed = not blocked

        return TruthGateDecision(
            allowed=allowed,
            blocked=blocked,
            rewritten=rewritten,
            violations=violations,
        )

    def apply(
        self,
        draft: str,
        evidence: EvidenceBundle,
        policy: TruthPolicy,
        *,
        fallback: str | None = None,
    ) -> str:
        d = self.evaluate(draft, evidence, policy)

        if d.rewritten is not None:
            return d.rewritten

        if d.allowed:
            return draft

        return fallback if fallback is not None else self.DEFAULT_BLOCK_MESSAGE
