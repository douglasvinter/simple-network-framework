"""Concurrent orchestration for heterogeneous discovery plugins."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Iterable
from typing import TYPE_CHECKING

from snf.models import DiscoveryEvent
from snf.plugins import DiscoveryPlugin
from snf.registry import DeviceRegistry

if TYPE_CHECKING:
    from snf.models import Device

_LOGGER = logging.getLogger(__name__)
_DONE = object()


class DiscoveryEngine:
    """Run protocol plugins concurrently and maintain a unified inventory."""

    def __init__(
        self,
        plugins: Iterable[DiscoveryPlugin],
        *,
        dedupe_cache_size: int = 4096,
        strict: bool = False,
    ) -> None:
        self._plugins = tuple(plugins)
        self._active_plugins: tuple[DiscoveryPlugin, ...] = ()
        self._strict = strict
        names = [plugin.name for plugin in self._plugins]
        if len(names) != len(set(names)):
            raise ValueError("Only one instance of each protocol plugin is allowed")
        if dedupe_cache_size < 1:
            raise ValueError("dedupe_cache_size must be at least 1")
        self._registry = DeviceRegistry(max_entries=dedupe_cache_size)
        self._started = False

    @property
    def devices(self) -> tuple[Device, ...]:
        """Return the current in-memory device inventory as an immutable snapshot."""
        return self._registry.snapshot()

    def get_device(self, protocol: str, identifier: str) -> Device | None:
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
            await self._stop_plugins(self._plugins)
            raise

        active: list[DiscoveryPlugin] = []
        failures: list[BaseException] = []
        for plugin, result in zip(self._plugins, results, strict=True):
            if isinstance(result, BaseException):
                failures.append(result)
                _LOGGER.error(
                    "Failed to start discovery plugin %s: %s",
                    plugin.name,
                    result,
                    exc_info=(type(result), result, result.__traceback__),
                )
                try:
                    await plugin.stop()
                except Exception:
                    _LOGGER.exception("Failed to clean up plugin %s after startup failure", plugin.name)
            else:
                active.append(plugin)

        if failures and self._strict:
            await self._stop_plugins(tuple(active))
            raise failures[0]

        self._active_plugins = tuple(active)
        self._started = True
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()

    async def _stop_plugins(self, plugins: tuple[DiscoveryPlugin, ...]) -> None:
        results = await asyncio.gather(
            *(plugin.stop() for plugin in reversed(plugins)),
            return_exceptions=True,
        )
        for plugin, result in zip(reversed(plugins), results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.warning("Failed to stop %s cleanly: %s", plugin.name, result)

    async def stop(self) -> None:
        """Stop every plugin even if one plugin fails during shutdown."""
        if not self._started:
            return
        self._started = False
        await self._stop_plugins(self._active_plugins)
        self._active_plugins = ()

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
        if not self._active_plugins:
            return

        queue: asyncio.Queue[object] = asyncio.Queue()
        tasks = [
            asyncio.create_task(self._pump(plugin, queue), name=f"snf:{plugin.name}")
            for plugin in self._active_plugins
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
