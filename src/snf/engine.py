"""Concurrent orchestration for heterogeneous discovery plugins."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Iterable

from snf.models import DiscoveryEvent
from snf.plugins import DiscoveryPlugin
from snf.registry import DeviceRegistry

_LOGGER = logging.getLogger(__name__)
_DONE = object()


class DiscoveryEngine:
    """Run protocol plugins concurrently and maintain a unified inventory."""

    def __init__(
        self,
        plugins: Iterable[DiscoveryPlugin],
        *,
        dedupe_cache_size: int = 4096,
    ) -> None:
        self._plugins = tuple(plugins)
        names = [plugin.name for plugin in self._plugins]
        if len(names) != len(set(names)):
            raise ValueError("Only one instance of each protocol plugin is allowed")
        if dedupe_cache_size < 1:
            raise ValueError("dedupe_cache_size must be at least 1")
        self._registry = DeviceRegistry(max_entries=dedupe_cache_size)
        self._started = False

    @property
    def devices(self):
        """Return the current in-memory device inventory as an immutable snapshot."""
        return self._registry.snapshot()

    def get_device(self, protocol: str, identifier: str):
        """Look up a device by its protocol-scoped identifier."""
        return self._registry.get(protocol, identifier)

    async def __aenter__(self) -> DiscoveryEngine:
        if self._started:
            raise RuntimeError("DiscoveryEngine is already running")

        try:
            results = await asyncio.gather(
                *(plugin.start() for plugin in self._plugins),
                return_exceptions=True,
            )
        except BaseException:
            await self._stop_plugins()
            raise

        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            await self._stop_plugins()
            raise failures[0]

        self._started = True
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()

    async def _stop_plugins(self) -> None:
        results = await asyncio.gather(
            *(plugin.stop() for plugin in reversed(self._plugins)),
            return_exceptions=True,
        )
        for plugin, result in zip(reversed(self._plugins), results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.warning("Failed to stop %s cleanly: %s", plugin.name, result)

    async def stop(self) -> None:
        """Stop every plugin even if one plugin fails during shutdown."""
        if not self._started:
            return
        self._started = False
        await self._stop_plugins()

    async def _pump(
        self, plugin: DiscoveryPlugin, queue: asyncio.Queue[object]
    ) -> None:
        _LOGGER.debug("Discovery pump started for plugin %s", plugin.name)
        try:
            async for event in plugin.discover():
                _LOGGER.debug(
                    "Plugin %s yielded %s device %s",
                    plugin.name,
                    event.state.value,
                    event.device.identifier,
                )
                await queue.put(event)
        except asyncio.CancelledError:
            _LOGGER.debug("Discovery pump cancelled for plugin %s", plugin.name)
            raise
        except Exception:
            _LOGGER.exception("Discovery plugin %s failed", plugin.name)
        finally:
            _LOGGER.debug("Discovery pump stopped for plugin %s", plugin.name)
            await queue.put(_DONE)

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        """Merge plugin streams and update the in-memory device inventory."""
        if not self._started:
            raise RuntimeError("Use DiscoveryEngine as an async context manager first")
        if not self._plugins:
            return

        queue: asyncio.Queue[object] = asyncio.Queue()
        tasks = [
            asyncio.create_task(self._pump(plugin, queue), name=f"snf:{plugin.name}")
            for plugin in self._plugins
        ]
        remaining = len(tasks)
        try:
            while remaining:
                item = await queue.get()
                if item is _DONE:
                    remaining -= 1
                    continue
                assert isinstance(item, DiscoveryEvent)
                normalized = self._registry.process(item)
                if normalized is not None:
                    yield normalized
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)
