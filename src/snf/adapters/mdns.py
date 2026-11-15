"""mDNS/DNS-SD adapter backed by python-zeroconf."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from importlib.util import find_spec
from typing import Any

from snf.models import Service, ServiceState

_LOGGER = logging.getLogger(__name__)

ALL_MDSNS_SERVICE_TYPES = [
  "_airplay._tcp.local.",
  "_raop._tcp.local.",
  "_googlecast._tcp.local.",
  "_spotify-connect._tcp.local.",
  "_sonos._tcp.local.",
  "_mediaremotetv._tcp.local.",
  "_daap._tcp.local.",
  "_dpap._tcp.local.",
  "_roon._tcp.local.",
  "_plexmediasvr._tcp.local.",
  "_hap._tcp.local.",
  "_homekit._tcp.local.",
  "_matter._tcp.local.",
  "_matterc._udp.local.",
  "_hue._tcp.local.",
  "_esphomelib._tcp.local.",
  "_mqtt._tcp.local.",
  "_home-assistant._tcp.local.",
  "_wled._tcp.local.",
  "_shelly._tcp.local.",
  "_ipp._tcp.local.",
  "_ipps._tcp.local.",
  "_printer._tcp.local.",
  "_pdl-datastream._tcp.local.",
  "_scanner._tcp.local.",
  "_uscan._tcp.local.",
  "_uscans._tcp.local.",
  "_smb._tcp.local.",
  "_afpovertcp._tcp.local.",
  "_nfs._tcp.local.",
  "_sftp-ssh._tcp.local.",
  "_ssh._tcp.local.",
  "_rfb._tcp.local.",
  "_http._tcp.local.",
  "_https._tcp.local.",
  "_workstation._tcp.local.",
  "_device-info._tcp.local.",
  "_occam._udp.local."
]

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
        self._events: asyncio.Queue[Service] = asyncio.Queue()
        self._zeroconf: Any = None
        self._browsers: list[Any] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        from zeroconf import InterfaceChoice
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconfServiceTypes, AsyncZeroconf

        self._loop = asyncio.get_running_loop()
        interfaces = self.interfaces if self.interfaces is not None else InterfaceChoice.All
        self._zeroconf = AsyncZeroconf(interfaces=interfaces)
        types = self.service_types
        if types is None:
            types = list(
                await AsyncZeroconfServiceTypes.async_find(
                    aiozc=self._zeroconf,
                    timeout=self.type_discovery_timeout,
                )
            )
        _LOGGER.debug("Discovered %d mDNS service types: %s", len(types), types)
        for service_type in types:
            _LOGGER.debug("Starting mDNS browser for %s", service_type)
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
        _LOGGER.debug(
            "mDNS browser reported %s for %s (%s)",
            state_change,
            name,
            service_type,
        )
        if self._loop is not None and not self._loop.is_closed():
            self._loop.create_task(self._resolve(service_type, name, state_change))

    async def _resolve(self, service_type: str, name: str, state_change: Any) -> None:
        from zeroconf import ServiceStateChange

        if state_change is ServiceStateChange.Removed:
            await self._events.put(
                Service(
                    protocol=self.name,
                    name=name,
                    address="",
                    service_type=service_type,
                    state=ServiceState.REMOVED,
                )
            )
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
        await self._events.put(
            Service(
                protocol=self.name,
                name=name,
                address=addresses[0],
                port=info.port,
                service_type=service_type,
                state=(
                    ServiceState.UPDATED
                    if state_change is ServiceStateChange.Updated
                    else ServiceState.ADDED
                ),
                metadata={
                    "server": info.server,
                    "addresses": addresses,
                    "properties": properties,
                },
            )
        )

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
