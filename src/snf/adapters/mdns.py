"""mDNS/DNS-SD adapter backed by python-zeroconf."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from importlib.util import find_spec
from typing import Any

from snf.models import DiscoveryObservation, DiscoveryEvent, DiscoveryState, Endpoint, Service

_LOGGER = logging.getLogger(__name__)

DEFAULT_SERVICE_TYPES = [
    "_airplay._tcp.local.", "_raop._tcp.local.", "_googlecast._tcp.local.",
    "_spotify-connect._tcp.local.", "_sonos._tcp.local.", "_mediaremotetv._tcp.local.",
    "_daap._tcp.local.", "_dpap._tcp.local.", "_roon._tcp.local.",
    "_plexmediasvr._tcp.local.", "_hap._tcp.local.", "_homekit._tcp.local.",
    "_matter._tcp.local.", "_matterc._udp.local.", "_hue._tcp.local.",
    "_esphomelib._tcp.local.", "_mqtt._tcp.local.", "_home-assistant._tcp.local.",
    "_wled._tcp.local.", "_shelly._tcp.local.", "_ipp._tcp.local.",
    "_ipps._tcp.local.", "_printer._tcp.local.", "_pdl-datastream._tcp.local.",
    "_scanner._tcp.local.", "_uscan._tcp.local.", "_uscans._tcp.local.",
    "_smb._tcp.local.", "_afpovertcp._tcp.local.", "_nfs._tcp.local.",
    "_sftp-ssh._tcp.local.", "_ssh._tcp.local.", "_rfb._tcp.local.",
    "_http._tcp.local.", "_https._tcp.local.", "_workstation._tcp.local.",
    "_device-info._tcp.local.", "_occam._udp.local.",
]

# Backward-compatible name retained for existing examples and integrations.
ALL_MDSNS_SERVICE_TYPES = DEFAULT_SERVICE_TYPES


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
                "Install mDNS support with: "
                "pip install 'simple-network-framework[mdns]'"
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

        properties = {
            (key.decode("utf-8", errors="replace") if isinstance(key, bytes) else str(key)):
            (
                value.decode("utf-8", errors="replace")
                if isinstance(value, bytes)
                else ("" if value is None else str(value))
            )
            for key, value in info.properties.items()
        }
        endpoints = tuple(Endpoint("ip", address, info.port) for address in addresses)
        service = Service(
            name=name,
            service_type=service_type,
            endpoints=endpoints,
            metadata={"server": info.server, "properties": properties},
        )
        device = DiscoveryObservation(
            protocol=self.name,
            identifier=identifier,
            name=name,
            endpoints=endpoints,
            services=(service,),
            metadata={"server": info.server, "properties": properties},
        )
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
