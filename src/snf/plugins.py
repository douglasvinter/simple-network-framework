"""Third-party protocol plugin contract and entry-point discovery."""

from __future__ import annotations

from importlib.metadata import EntryPoint, entry_points
from typing import Protocol, runtime_checkable
from collections.abc import AsyncIterator

from snf.models import Service


@runtime_checkable
class DiscoveryPlugin(Protocol):
    """Contract implemented by every SNF protocol adapter."""

    name: str

    async def start(self) -> None:
        """Allocate resources and begin listening."""

    def discover(self) -> AsyncIterator[Service]:
        """Yield service lifecycle events until stopped."""

    async def stop(self) -> None:
        """Stop discovery and release all owned resources."""


def load_plugins() -> dict[str, type[DiscoveryPlugin]]:
    """Load classes registered in the snf.protocols entry-point group."""
    loaded: dict[str, type[DiscoveryPlugin]] = {}
    candidates: list[EntryPoint] = sorted(entry_points(group="snf.protocols"), key=lambda ep: ep.name)

    for entry_point in candidates:
        if entry_point.name in loaded:
            raise RuntimeError(f"Duplicate SNF protocol plugin: {entry_point.name}")
        plugin = entry_point.load()
        if not isinstance(plugin, type):
            raise TypeError(f"Plugin entry point {entry_point.name!r} must resolve to a class")
        for method in ("start", "discover", "stop"):
            if not callable(getattr(plugin, method, None)):
                raise TypeError(f"Plugin {entry_point.name!r} is missing {method}()")
        loaded[entry_point.name] = plugin
    return loaded
