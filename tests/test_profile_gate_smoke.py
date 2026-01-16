from __future__ import annotations

from ashby.core.profile import ConsentRecord, EgressPlan, ExecutionProfile, evaluate_profile


def test_profile_gate_smoke_all_profiles() -> None:
    egress = EgressPlan(
        provider="openai",
        endpoint=None,
        data_categories={"text", "metadata"},
        purpose="llm_completion",
        retention="unknown",
    )

    # LOCAL_ONLY denies egress
    d = evaluate_profile(ExecutionProfile.LOCAL_ONLY, egress, None)
    assert d.allowed is False
    assert d.requires_consent is False
    assert d.denied_reason == "LOCAL_ONLY forbids network egress"

    # HYBRID requires consent
    d = evaluate_profile(ExecutionProfile.HYBRID, egress, None)
    assert d.allowed is False
    assert d.requires_consent is True
    assert d.required_disclosure is not None and len(d.required_disclosure) > 0

    # HYBRID allows when consent matches (provider match + categories superset)
    consent = ConsentRecord(
        granted=True,
        disclosure_text="ok",
        user_confirmed_at="2026-01-01T00:00:00Z",
        scope={"run_id": "r1"},
        provider="openai",
        data_categories=["text", "metadata", "image"],
    )
    d = evaluate_profile(ExecutionProfile.HYBRID, egress, consent)
    assert d.allowed is True
    assert d.requires_consent is False

    # HYBRID mismatch provider -> treat as no consent
    consent_bad_provider = ConsentRecord(
        granted=True,
        disclosure_text="ok",
        user_confirmed_at="2026-01-01T00:00:00Z",
        scope={"run_id": "r1"},
        provider="anthropic",
        data_categories=["text", "metadata", "image"],
    )
    d = evaluate_profile(ExecutionProfile.HYBRID, egress, consent_bad_provider)
    assert d.allowed is False
    assert d.requires_consent is True

    # HYBRID mismatch categories -> treat as no consent
    consent_bad_cats = ConsentRecord(
        granted=True,
        disclosure_text="ok",
        user_confirmed_at="2026-01-01T00:00:00Z",
        scope={"run_id": "r1"},
        provider="openai",
        data_categories=["text"],  # missing metadata
    )
    d = evaluate_profile(ExecutionProfile.HYBRID, egress, consent_bad_cats)
    assert d.allowed is False
    assert d.requires_consent is True

    # CLOUD allows egress
    d = evaluate_profile(ExecutionProfile.CLOUD, egress, None)
    assert d.allowed is True
    assert d.requires_consent is False

    # No egress planned is always allowed (even LOCAL_ONLY)
    d = evaluate_profile(ExecutionProfile.LOCAL_ONLY, None, None)
    assert d.allowed is True
    assert d.requires_consent is False

    empty_egress = EgressPlan(
        provider="openai",
        endpoint=None,
        data_categories=set(),
        purpose="noop",
        retention=None,
    )
    d = evaluate_profile(ExecutionProfile.LOCAL_ONLY, empty_egress, None)
    assert d.allowed is True
    assert d.requires_consent is False
