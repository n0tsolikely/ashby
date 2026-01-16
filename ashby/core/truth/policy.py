from __future__ import annotations

from typing import Protocol

from ashby.core import truth_gate as legacy_truth_gate

from .evidence import EvidenceBundle, TruthViolation


class TruthPolicy(Protocol):
    """
    TruthPolicy defines how to validate and optionally rewrite a draft given evidence.

    Batch 0 contract:
    - validate() is deterministic and side-effect-free
    - rewrite() may return rewritten string or None
    """
    policy_id: str

    def validate(self, draft: str, evidence: EvidenceBundle) -> list[TruthViolation]:
        ...

    def rewrite(
        self,
        draft: str,
        evidence: EvidenceBundle,
        violations: list[TruthViolation],
    ) -> str | None:
        ...


class ForbiddenPhrasesPolicy:
    """
    Compatibility bridge policy.

    MUST replicate legacy phrase list + reject string from ashby.core.truth_gate.
    """
    policy_id = "forbidden_phrases_v1"

    def __init__(
        self,
        *,
        phrases: list[str] | None = None,
        reject: str | None = None,
    ) -> None:
        if phrases is None:
            phrases = list(legacy_truth_gate.FORBIDDEN_PHRASES)
        if reject is None:
            reject = legacy_truth_gate.DEFAULT_REJECT

        self._phrases = tuple(str(p) for p in phrases)
        self._reject = str(reject)

    @property
    def phrases(self) -> tuple[str, ...]:
        return self._phrases

    @property
    def reject(self) -> str:
        return self._reject

    def validate(self, draft: str, evidence: EvidenceBundle) -> list[TruthViolation]:
        if not isinstance(draft, str):
            raise TypeError("draft must be a str")

        low = (draft or "").lower()
        matches = [p for p in self._phrases if p in low]

        if not matches:
            return []

        return [
            TruthViolation(
                code="FORBIDDEN_PHRASE",
                message=f"Forbidden phrase detected: {matches[0]}",
                severity="block",
                evidence_required=False,
                meta={"matches": matches},
            )
        ]

    def rewrite(
        self,
        draft: str,
        evidence: EvidenceBundle,
        violations: list[TruthViolation],
    ) -> str | None:
        for v in violations:
            if v.code == "FORBIDDEN_PHRASE":
                return self._reject
        return None
