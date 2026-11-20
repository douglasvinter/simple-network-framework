"""mDNS/DNS-SD adapter backed by python-zeroconf."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from importlib.resources import files
from importlib.util import find_spec
from typing import Any

from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState, Endpoint, Service

_LOGGER = logging.getLogger(__name__)

with files("snf").joinpath("adapters", "mdns_service_types.json").open(
    "r", encoding="utf-8"
) as _catalog:
    DEFAULT_SERVICE_TYPES: list[str] = json.load(_catalog)

# Backward-compatible name retained for existing examples and integrations.
ALL_MDSNS_SERVICE_TYPES = DEFAULT_SERVICE_TYPES


def _decode_properties(properties: dict[Any, Any]) -> dict[str, str]:
    """Normalize DNS-SD TXT properties using the existing replacement policy."""
    return {
        (key.decode("utf-8", errors="replace") if isinstance(key, bytes) else str(key)): (
            value.decode("utf-8", errors="replace")
            if isinstance(value, bytes)
            else ("" if value is None else str(value))
        )
        for key, value in properties.items()
    }


def _observation_from_service_info(
    service_type: str, name: str, info: Any, addresses: list[str]
) -> DiscoveryObservation:
    """Project resolved DNS-SD records without owning resolution or event emission."""
    identifier = f"{service_type}|{name}"
    properties = _decode_properties(info.properties)
    endpoints = tuple(Endpoint("ip", address, info.port) for address in addresses)
    service = Service(
        name=name,
        service_type=service_type,
        endpoints=endpoints,
        metadata={"server": info.server, "properties": properties},
    )
    return DiscoveryObservation(
        protocol=self.name,
        identifier=identifier,
        name=name,
        endpoints=endpoints,
        services=(service,),
        metadata={"server": info.server, "properties": properties},
    )

class MDNSPlugin:
    """Browse and resolve DNS-SD service instances."""

    name = "mdns"

    def __init__(
        self,
        service_types: list[str] | None = None,
        *,
        resolve_timeout: int = 3000,
        interfaces: Any = None,
        type_discovery_timeout: float = 3.0,
    ) -> None:
        if find_spec("zeroconf") is None:
            raise ImportError(
                "Install mDNS support with: pip install 'simple-network-framework[mdns]'"
            )
        self.service_types = service_types
        self.resolve_timeout = resolve_timeout
        self.interfaces = interfaces
        self.type_discovery_timeout = type_discovery_timeout
        self._events: asyncio.Queue[DiscoveryEvent | None] = asyncio.Queue()
        self._zeroconf: Any = None
        self._browsers: list[Any] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        from zeroconf import InterfaceChoice
        from zeroconf.asyncio import (
            AsyncServiceBrowser,
            AsyncZeroconf,
            AsyncZeroconfServiceTypes,
        )

        self._events = asyncio.Queue()
        self._loop = asyncio.get_running_loop()
        interfaces = self.interfaces if self.interfaces is not None else InterfaceChoice.All
        self._zeroconf = AsyncZeroconf(interfaces=interfaces)
        types = self.service_types
        if types is None:
            types = list(
                await AsyncZeroconfServiceTypes.async_find(
                    aiozc=self._zeroconf, timeout=self.type_discovery_timeout
                )
            )
        _LOGGER.debug("Discovered %d mDNS service types: %s", len(types), types)
        for service_type in types:
            self._browsers.append(
                AsyncServiceBrowser(
                    self._zeroconf.zeroconf,
                    service_type,
                    handlers=[self._on_service_state_change],
                )
            )

    def _on_service_state_change(
        self, zeroconf: Any, service_type: str, name: str, state_change: Any
    ) -> None:
        _LOGGER.debug("mDNS reported %s for %s (%s)", state_change, name, service_type)
        if self._loop is not None and not self._loop.is_closed():
            self._loop.create_task(self._resolve(service_type, name, state_change))

    async def _resolve(self, service_type: str, name: str, state_change: Any) -> None:
        from zeroconf import ServiceStateChange

        identifier = f"{service_type}|{name}"
        if state_change is ServiceStateChange.Removed:
            device = DiscoveryObservation(self.name, identifier, name)
            await self._events.put(DiscoveryEvent(DiscoveryState.REMOVED, device))
            return

        info = await self._zeroconf.async_get_service_info(
            service_type, name, timeout=self.resolve_timeout
        )
        if info is None:
            return
        addresses = info.parsed_addresses()
        if not addresses:
            return

        device = _observation_from_service_info(service_type, name, info, addresses)
        await self._events.put(DiscoveryEvent(DiscoveryState.ADDED, device))

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        if self._zeroconf is None:
            raise RuntimeError("MDNSPlugin.start() must be called before discover()")
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def stop(self) -> None:
        for browser in self._browsers:
            await browser.async_cancel()
        self._browsers.clear()
        self._events.put_nowait(None)
        if self._zeroconf is not None:
            await self._zeroconf.async_close()
            self._zeroconf = None
