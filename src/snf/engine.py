"""Concurrent orchestration for installed discovery plugins."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Iterable

from snf.models import Service
from snf.plugins import DiscoveryPlugin
from snf.registry import ServiceRegistry

_LOGGER = logging.getLogger(__name__)
_DONE = object()


class DiscoveryEngine:
    """Run multiple protocol plugins behind one asynchronous interface."""

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
        self._dedupe_cache_size = dedupe_cache_size
        self._started = False

    async def __aenter__(self) -> DiscoveryEngine:
        if self._started:
            raise RuntimeError("DiscoveryEngine is already running")

        try:
            results = await asyncio.gather(
                *(plugin.start() for plugin in self._plugins),
                return_exceptions=True,
            )
        except BaseException:
            # A cancelled or interrupted startup may have left plugins with
            # partially allocated resources. Ask every plugin to clean up.
            await self._stop_plugins()
            raise

        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            # Stop all plugins, including the one whose start() failed: it may
            # have allocated resources before raising.
            await self._stop_plugins()
            raise failures[0]

        self._started = True
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()

    async def _stop_plugins(self) -> None:
        """Stop every plugin, logging failures without skipping other plugins."""
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

    async def _pump(self, plugin: DiscoveryPlugin, queue: asyncio.Queue[object]) -> None:
        try:
            async for service in plugin.discover():
                await queue.put(service)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Discovery plugin %s failed", plugin.name)
        finally:
            await queue.put(_DONE)

    async def discover(self) -> AsyncIterator[Service]:
        """Merge plugin streams and suppress duplicate service announcements."""
        if not self._started:
            raise RuntimeError("Use DiscoveryEngine as an async context manager first")
        if not self._plugins:
            return

        queue: asyncio.Queue[object] = asyncio.Queue()
        registry = ServiceRegistry(max_entries=self._dedupe_cache_size)
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
                else:
                    assert isinstance(item, Service)
                    event = registry.process(item)
                    if event is not None:
                        yield event
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)
