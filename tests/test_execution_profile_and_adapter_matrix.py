from __future__ import annotations

from ashby.core.profile import ExecutionProfile, get_execution_profile
from ashby.modules.meetings.adapters.adapter_matrix import get_meetings_adapter_matrix


def test_default_profile_is_local_only(monkeypatch):
    monkeypatch.delenv("ASHBY_EXECUTION_PROFILE", raising=False)
    assert get_execution_profile() == ExecutionProfile.LOCAL_ONLY


def test_adapter_matrix_returns_callables(monkeypatch):
    monkeypatch.delenv("ASHBY_EXECUTION_PROFILE", raising=False)
    prof = get_execution_profile()
    mat = get_meetings_adapter_matrix(prof)
    assert mat.profile == ExecutionProfile.LOCAL_ONLY
    assert callable(mat.transcribe)
    assert callable(mat.diarize)
    assert callable(mat.pdf)
    assert callable(mat.normalize)
    assert callable(mat.align)


def test_execution_profiles_shim_exports_canonical_type():
    # Legacy module should be a thin re-export, not a parallel enum.
    import ashby.core.execution_profiles as shim_mod
    import ashby.core.profile as profile_mod

    assert shim_mod.ExecutionProfile is profile_mod.ExecutionProfile
    assert shim_mod.get_execution_profile is profile_mod.get_execution_profile
