from __future__ import annotations

import pytest

from ashby.core.module_registry import ModuleRegistry, ModuleRegistryError, ModuleSpec


class _Toy:
    def __init__(self, x: int = 0) -> None:
        self.x = x


def test_module_registry_smoke() -> None:
    r = ModuleRegistry()

    spec = ModuleSpec(
        module_id="stuart",
        name="Stuart",
        version="0.1.0",
        description="Meeting assistant",
        factory=lambda **kw: _Toy(**kw),
    )

    r.register(spec)
    assert r.list_ids() == ["stuart"]
    assert r.get("stuart").name == "Stuart"

    inst = r.create("stuart", x=7)
    assert isinstance(inst, _Toy)
    assert inst.x == 7

    with pytest.raises(ModuleRegistryError):
        r.get("missing")

    with pytest.raises(ModuleRegistryError):
        r.register(spec)
