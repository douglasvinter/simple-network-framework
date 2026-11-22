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
    decoded: dict[str, str] = {}

    for key, value in properties.items():
        if isinstance(key, bytes):
            decoded_key = key.decode("utf-8", errors="replace")
        else:
            decoded_key = str(key)
        if isinstance(value, bytes):
            decoded_value = value.decode("utf-8", errors="replace")
        elif value is None:
            decoded_value = ""
        else:
            decoded_value = str(value)

        decoded[decoded_key] = decoded_value

    return decoded


def _observation_from_service_info(
    service_type: str, name: str, info: Any, addresses: list[str], *, protocol: str = "mdns"
) -> DiscoveryObservation:
    """Project resolved DNS-SD records without owning resolution or event emission."""
    identifier = f"{service_type}|{name}"
    properties = _decode_properties(info.properties)
    endpoints = tuple(Endpoint("ip", address, info.port) for address in addresses)
    metadata = {"server": info.server, "properties": properties}

    service = Service(
        name=name,
        service_type=service_type,
        endpoints=endpoints,
        metadata=metadata,
    )
    return DiscoveryObservation(
        protocol=protocol,
        identifier=identifier,
        name=name,
        endpoints=endpoints,
        services=(service,),
        metadata=metadata.copy(),
    )


class MDNSPlugin:
    """Browse DNS-SD service instances and publish resolved observations.

    Service types can be configured explicitly or discovered at startup.
    """

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

    async def _service_types_to_browse(self) -> list[str]:
        """Return configured service types, or discover them through Zeroconf."""
        from zeroconf.asyncio import AsyncZeroconfServiceTypes

        if self.service_types is not None:
            return self.service_types

        return list(
            await AsyncZeroconfServiceTypes.async_find(
                aiozc=self._zeroconf,
                timeout=self.type_discovery_timeout,
            )
        )

    def _register_browsers(self, service_types: list[str]) -> None:
        """Register the discovery callback for each selected service type."""
        from zeroconf.asyncio import AsyncServiceBrowser

        for service_type in service_types:
            self._browsers.append(
                AsyncServiceBrowser(
                    self._zeroconf.zeroconf,
                    service_type,
                    handlers=[self._on_service_state_change],
                )
            )

    async def start(self) -> None:
        """Initialize Zeroconf and begin browsing the selected service types."""
        from zeroconf import InterfaceChoice
        from zeroconf.asyncio import AsyncZeroconf

        self._events = asyncio.Queue()
        self._loop = asyncio.get_running_loop()

        interfaces = self.interfaces if self.interfaces is not None else InterfaceChoice.All
        self._zeroconf = AsyncZeroconf(interfaces=interfaces)

        service_types = await self._service_types_to_browse()
        _LOGGER.debug("Discovered %d mDNS service types: %s", len(service_types), service_types)
        self._register_browsers(service_types)

    def _on_service_state_change(
        self, zeroconf: Any, service_type: str, name: str, state_change: Any
    ) -> None:
        _LOGGER.debug("mDNS reported %s for %s (%s)", state_change, name, service_type)
        if self._loop is not None and not self._loop.is_closed():
            self._loop.create_task(self._resolve(service_type, name, state_change))

    async def _resolve(self, service_type: str, name: str, state_change: Any) -> None:
        from zeroconf import ServiceStateChange

        if state_change is ServiceStateChange.Removed:
            identifier = f"{service_type}|{name}"
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

        device = _observation_from_service_info(
            service_type, name, info, addresses, protocol=self.name
        )
        await self._events.put(DiscoveryEvent(DiscoveryState.ADDED, device))

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        """Yield discovery events until the adapter is stopped."""
        if self._zeroconf is None:
            raise RuntimeError("MDNSPlugin.start() must be called before discover()")
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def stop(self) -> None:
        """Cancel browsers, close Zeroconf, and end the discovery stream."""
        for browser in self._browsers:
            await browser.async_cancel()
        self._browsers.clear()
        self._events.put_nowait(None)
        if self._zeroconf is not None:
            await self._zeroconf.async_close()
            self._zeroconf = None
