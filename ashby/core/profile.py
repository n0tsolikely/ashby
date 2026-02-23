from __future__ import annotations

import os

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, TypeAlias


class ExecutionProfile(str, Enum):
    """
    Canonical execution profiles (Batch 0).

    EXACT values:
    - LOCAL_ONLY
    - HYBRID
    - CLOUD
    """

    LOCAL_ONLY = "LOCAL_ONLY"
    HYBRID = "HYBRID"
    CLOUD = "CLOUD"



def get_execution_profile() -> ExecutionProfile:
    """Return the active execution profile.

    Rule:
    - Reads ASHBY_EXECUTION_PROFILE from env.
    - Defaults to LOCAL_ONLY.
    - Invalid values fall back to LOCAL_ONLY (truthful + safe).
    """
    raw = (os.environ.get("ASHBY_EXECUTION_PROFILE") or "").strip().upper()
    try:
        return ExecutionProfile(raw) if raw else ExecutionProfile.LOCAL_ONLY
    except Exception:
        return ExecutionProfile.LOCAL_ONLY



DataCategory: TypeAlias = Literal["audio", "transcript", "text", "image", "metadata"]

_ALLOWED_CATEGORIES: set[str] = {"audio", "transcript", "text", "image", "metadata"}


def _require_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")
    if value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")
    return value


def _optional_str(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str or None")
    return value


def _require_dict(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")
    return value


def _coerce_categories_to_set(value: Any, *, field_name: str) -> set[DataCategory]:
    if value is None:
        return set()

    if isinstance(value, set):
        raw = value
    elif isinstance(value, (list, tuple, frozenset)):
        raw = set(value)
    else:
        raise TypeError(f"{field_name} must be a set/list/tuple of DataCategory")

    out: set[DataCategory] = set()
    for item in raw:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be str")
        if item not in _ALLOWED_CATEGORIES:
            raise ValueError(f"invalid data category: {item}")
        out.add(item)  # type: ignore[arg-type]
    return out


def _coerce_categories_to_list(value: Any, *, field_name: str) -> list[DataCategory]:
    if value is None:
        return []

    if isinstance(value, list):
        raw = value
    elif isinstance(value, (set, tuple, frozenset)):
        raw = list(value)
    else:
        raise TypeError(f"{field_name} must be a list/set/tuple of DataCategory")

    out: list[DataCategory] = []
    for item in raw:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be str")
        if item not in _ALLOWED_CATEGORIES:
            raise ValueError(f"invalid data category: {item}")
        out.append(item)  # type: ignore[arg-type]
    return out


@dataclass
class EgressPlan:
    """
    Represents a specific planned network egress.
    """

    provider: str
    endpoint: str | None
    data_categories: set[DataCategory]
    purpose: str
    retention: str | None

    def __post_init__(self) -> None:
        self.provider = _require_str(self.provider, field_name="provider")
        self.endpoint = _optional_str(self.endpoint, field_name="endpoint")
        self.purpose = _require_str(self.purpose, field_name="purpose")
        self.retention = _optional_str(self.retention, field_name="retention")
        self.data_categories = _coerce_categories_to_set(self.data_categories, field_name="data_categories")


@dataclass
class ConsentRecord:
    """
    Represents user consent for an egress plan.
    """

    granted: bool
    disclosure_text: str
    user_confirmed_at: str | None
    scope: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    data_categories: list[DataCategory] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.granted, bool):
            raise TypeError("granted must be a bool")
        self.disclosure_text = _require_str(self.disclosure_text, field_name="disclosure_text")
        self.user_confirmed_at = _optional_str(self.user_confirmed_at, field_name="user_confirmed_at")
        self.scope = _require_dict(self.scope, field_name="scope")
        self.provider = _require_str(self.provider, field_name="provider")
        self.data_categories = _coerce_categories_to_list(self.data_categories, field_name="data_categories")

        if self.granted and self.user_confirmed_at is None:
            raise ValueError("user_confirmed_at must be set when granted=True")


@dataclass
class ProfileGateDecision:
    allowed: bool
    requires_consent: bool
    denied_reason: str | None
    required_disclosure: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise TypeError("allowed must be a bool")
        if not isinstance(self.requires_consent, bool):
            raise TypeError("requires_consent must be a bool")

        if self.allowed:
            if self.denied_reason is not None:
                raise ValueError("allowed=True must have denied_reason=None")
            if self.required_disclosure is not None:
                raise ValueError("allowed=True must have required_disclosure=None")

        if self.requires_consent:
            if self.allowed:
                raise ValueError("requires_consent=True cannot have allowed=True")
            if self.required_disclosure is None or self.required_disclosure.strip() == "":
                raise ValueError("requires_consent=True must provide required_disclosure")


def _disclosure_for(egress: EgressPlan) -> str:
    cats = ", ".join(sorted(egress.data_categories))
    endpoint = egress.endpoint if egress.endpoint is not None else "unspecified"
    retention = egress.retention if egress.retention is not None else "unknown"
    return (
        f"Network egress planned: provider={egress.provider}; endpoint={endpoint}; "
        f"purpose={egress.purpose}; data_categories=[{cats}]; retention={retention}."
    )


def evaluate_profile(
    profile: ExecutionProfile,
    egress: EgressPlan | None,
    consent: ConsentRecord | None,
) -> ProfileGateDecision:
    """
    Canonical evaluation helper (Batch 0).

    Rules:
    - If egress is None or data_categories empty: always allowed
    - LOCAL_ONLY: deny any egress
    - HYBRID: requires explicit consent that matches provider + categories superset
    - CLOUD: allow egress
    """
    # No network egress planned.
    if egress is None or len(egress.data_categories) == 0:
        return ProfileGateDecision(
            allowed=True,
            requires_consent=False,
            denied_reason=None,
            required_disclosure=None,
        )

    if profile == ExecutionProfile.LOCAL_ONLY:
        return ProfileGateDecision(
            allowed=False,
            requires_consent=False,
            denied_reason="LOCAL_ONLY forbids network egress",
            required_disclosure=None,
        )

    if profile == ExecutionProfile.CLOUD:
        return ProfileGateDecision(
            allowed=True,
            requires_consent=False,
            denied_reason=None,
            required_disclosure=None,
        )

    if profile != ExecutionProfile.HYBRID:
        raise ValueError(f"Unknown ExecutionProfile: {profile}")

    # HYBRID
    required_disclosure = _disclosure_for(egress)

    if consent is None or consent.granted is False:
        return ProfileGateDecision(
            allowed=False,
            requires_consent=True,
            denied_reason="Consent required for network egress",
            required_disclosure=required_disclosure,
        )

    # Consent exists + granted: must match provider + categories superset.
    consent_cats = set(consent.data_categories)
    if consent.provider != egress.provider:
        return ProfileGateDecision(
            allowed=False,
            requires_consent=True,
            denied_reason="Consent does not match egress provider",
            required_disclosure=required_disclosure,
        )

    if not consent_cats.issuperset(egress.data_categories):
        return ProfileGateDecision(
            allowed=False,
            requires_consent=True,
            denied_reason="Consent does not cover required data categories",
            required_disclosure=required_disclosure,
        )

    return ProfileGateDecision(
        allowed=True,
        requires_consent=False,
        denied_reason=None,
        required_disclosure=None,
    )
