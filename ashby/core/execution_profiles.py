from __future__ import annotations

"""Deprecated shim module.

This file exists only for backwards compatibility with older imports.

Canonical execution profile + selection helper live in:
  ashby.core.profile

Do NOT add new business logic here.
"""

from ashby.core.profile import ExecutionProfile, get_execution_profile

__all__ = [
    "ExecutionProfile",
    "get_execution_profile",
]
