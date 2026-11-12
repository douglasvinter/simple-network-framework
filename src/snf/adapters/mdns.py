"""mDNS/DNS-SD adapter backed by python-zeroconf."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from importlib.util import find_spec
from typing import Any

from snf.models import Service, ServiceState


class MDNSPlugin:
    """Browse and resolve DNS-SD service instances."""

    name = "mdns"

    def __init__(self, service_types: list[str] | None = None, *, resolve_timeout: int = 3000,
                 interfaces: Any = None, type_discovery_timeout: float = 3.0) -> None:
        if find_spec("zeroconf") is None:
            raise ImportError("Install mDNS support with: pip install 'simple-network-framework[mdns]'")
        self.service_types = service_types
        self.resolve_timeout = resolve_timeout
        self.interfaces = interfaces
        self.type_discovery_timeout = type_discovery_timeout
        self._events: asyncio.Queue[Service] = asyncio.Queue()
        self._zeroconf: Any = None
        self._browsers: list[Any] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        from zeroconf import InterfaceChoice
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceTypes, AsyncZeroconf

        self._loop = asyncio.get_running_loop()
        interfaces = self.interfaces if self.interfaces is not None else InterfaceChoice.All
        self._zeroconf = AsyncZeroconf(interfaces=interfaces)
        types = self.service_types
        if types is None:
            types = list(await AsyncServiceTypes.async_find(
                aiozc=self._zeroconf, timeout=self.type_discovery_timeout
            ))
        for service_type in types:
            self._browsers.append(AsyncServiceBrowser(
                self._zeroconf.zeroconf, service_type, handlers=[self._on_service_state_change]
            ))

    def _on_service_state_change(self, zeroconf: Any, service_type: str, name: str,
                                 state_change: Any) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.create_task(self._resolve(service_type, name, state_change))

    async def _resolve(self, service_type: str, name: str, state_change: Any) -> None:
        from zeroconf import ServiceStateChange

        if state_change is ServiceStateChange.Removed:
            await self._events.put(Service(
                protocol=self.name, name=name, address="", service_type=service_type,
                state=ServiceState.REMOVED,
            ))
            return
        info = await self._zeroconf.async_get_service_info(
            service_type, name, timeout=self.resolve_timeout
        )
        if info is None:
            return
        addresses = info.parsed_addresses()
        if not addresses:
            return
        properties = {
            (key.decode("utf-8", errors="replace") if isinstance(key, bytes) else str(key)):
            (value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value))
            for key, value in info.properties.items()
        }
        await self._events.put(Service(
            protocol=self.name, name=name, address=addresses[0], port=info.port,
            service_type=service_type,
            state=ServiceState.UPDATED if state_change is ServiceStateChange.Updated else ServiceState.ADDED,
            metadata={"server": info.server, "addresses": addresses, "properties": properties},
        ))

    async def discover(self) -> AsyncIterator[Service]:
        if self._zeroconf is None:
            raise RuntimeError("MDNSPlugin.start() must be called before discover()")
        while True:
            yield await self._events.get()

    async def stop(self) -> None:
        for browser in self._browsers:
            await browser.async_cancel()
        self._browsers.clear()
        if self._zeroconf is not None:
            await self._zeroconf.async_close()
            self._zeroconf = None
