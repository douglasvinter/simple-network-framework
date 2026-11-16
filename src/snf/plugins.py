"""Third-party discovery plugin contract and entry-point loading."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from importlib.metadata import EntryPoint, entry_points
from typing import Protocol, runtime_checkable

from snf.models import DiscoveryEvent

_LOGGER = logging.getLogger(__name__)


@runtime_checkable
class DiscoveryPlugin(Protocol):
    """Contract implemented by every SNF discovery adapter."""

    name: str

    async def start(self) -> None:
        """Allocate resources and begin observing the protocol."""

    def discover(self) -> AsyncIterator[DiscoveryEvent]:
        """Yield device lifecycle events until stopped."""

    async def stop(self) -> None:
        """Stop discovery and release all owned resources."""


def load_plugins() -> dict[str, type[DiscoveryPlugin]]:
    """Load valid plugin classes, logging and isolating individual failures.

    An entry point can fail before its plugin class is imported (for example,
    because a module-level optional dependency is missing). In that case the
    loader is the only component able to report the failure.
    """
    loaded: dict[str, type[DiscoveryPlugin]] = {}
    candidates: list[EntryPoint] = sorted(
        entry_points(group="snf.protocols"), key=lambda entry_point: entry_point.name
    )

    for entry_point in candidates:
        if entry_point.name in loaded:
            _LOGGER.error(
                "Skipping duplicate SNF protocol plugin entry point %r",
                entry_point.name,
            )
            continue

        try:
            plugin = entry_point.load()
            if not isinstance(plugin, type):
                raise TypeError("entry point must resolve to a plugin class")
            for method in ("start", "discover", "stop"):
                if not callable(getattr(plugin, method, None)):
                    raise TypeError(f"plugin class is missing {method}()")
        except Exception:
            _LOGGER.exception(
                "Failed to load SNF protocol plugin %r from %s",
                entry_point.name,
                entry_point.value,
            )
            continue

        loaded[entry_point.name] = plugin
        _LOGGER.debug("Loaded SNF protocol plugin %r", entry_point.name)

    return loaded
