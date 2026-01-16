from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class ModuleRegistryError(Exception):
    pass


@dataclass(frozen=True, kw_only=True)
class ModuleSpec:
    """
    Canonical module metadata + factory.

    Batch 0 contract:
    - module_id is unique (string)
    - version is a string (semver-ish, not enforced)
    - factory is callable with **kwargs and returns module instance
    """
    module_id: str
    name: str
    version: str
    description: str | None = None
    factory: Callable[..., Any] = field(repr=False, default=lambda **_: None)

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or self.module_id.strip() == "":
            raise ValueError("module_id must be a non-empty str")
        if not isinstance(self.name, str) or self.name.strip() == "":
            raise ValueError("name must be a non-empty str")
        if not isinstance(self.version, str) or self.version.strip() == "":
            raise ValueError("version must be a non-empty str")
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("description must be a str or None")
        if not callable(self.factory):
            raise TypeError("factory must be callable")


class ModuleRegistry:
    """
    In-memory registry.

    Batch 0: simple deterministic map.
    Later: can load from config / plugin discovery / signed manifests.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ModuleSpec] = {}

    def register(self, spec: ModuleSpec) -> None:
        if not isinstance(spec, ModuleSpec):
            raise TypeError("spec must be a ModuleSpec")
        key = spec.module_id

        if key in self._specs:
            existing = self._specs[key]
            raise ModuleRegistryError(
                f"Module already registered: {key} ({existing.name} {existing.version})"
            )

        self._specs[key] = spec

    def get(self, module_id: str) -> ModuleSpec:
        if not isinstance(module_id, str) or module_id.strip() == "":
            raise ValueError("module_id must be a non-empty str")
        try:
            return self._specs[module_id]
        except KeyError as e:
            raise ModuleRegistryError(f"Module not found: {module_id}") from e

    def list_ids(self) -> list[str]:
        return sorted(self._specs.keys())

    def create(self, module_id: str, **kwargs: Any) -> Any:
        spec = self.get(module_id)
        return spec.factory(**kwargs)
