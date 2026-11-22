"""SSDP adapter backed by async-upnp-client."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import AsyncIterator, Mapping
from importlib.util import find_spec

from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState, Endpoint, Service

_LOGGER = logging.getLogger(__name__)


def _default_route_ipv4() -> str:
    """Find the IPv4 source address selected by the OS default route.

    UDP connect() performs route selection without sending a datagram.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("1.1.1.1", 9))
        address = sock.getsockname()[0]
    if address == "0.0.0.0":
        raise OSError("Unable to determine the default-route IPv4 address")
    return str(address)


def _observation_from_response(headers: Mapping[str, object]) -> DiscoveryObservation | None:
    """Convert an SSDP response into a protocol-scoped observation."""
    values = {str(key).lower(): value for key, value in dict(headers).items()}
    host = str(values.get("_host", ""))
    if not host:
        return None

    raw_port = values.get("_port")
    port = int(raw_port) if isinstance(raw_port, (str, int, bytes, bytearray)) else None
    usn = str(values.get("usn", ""))
    location = values.get("location")
    identifier = usn or str(location or host)
    udn = usn.split("::", 1)[0] if usn.lower().startswith("uuid:") else None

    endpoint = Endpoint("ip", host, port)
    service = Service(
        name=identifier,
        service_type=str(values.get("st", "")) or None,
        endpoints=(endpoint,),
        metadata=values,
    )
    return DiscoveryObservation(
        protocol="ssdp",
        identifier=identifier,
        name=str(values.get("server") or values.get("st") or identifier),
        endpoints=(endpoint,),
        services=(service,),
        metadata={"location": location, "usn": usn, "udn": udn},
    )


class SSDPPlugin:
    """Discover UPnP devices through the async-upnp-client search API."""

    name = "ssdp"

    def __init__(
        self,
        *,
        search_target: str = "ssdp:all",
        search_interval: float = 30.0,
        search_timeout: int = 5,
    ) -> None:
        if search_interval <= 0:
            raise ValueError("search_interval must be positive")
        if not 1 <= search_timeout <= 120:
            raise ValueError("search_timeout must be between 1 and 120 seconds")
        if find_spec("async_upnp_client") is None:
            raise ImportError(
                "Install SSDP support with: pip install 'simple-network-framework[ssdp]'"
            )
        self.search_target = search_target
        self.search_interval = search_interval
        self.search_timeout = search_timeout
        self._running = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._running = True
        self._stop_event.clear()

    async def _search(self) -> asyncio.Queue[DiscoveryEvent]:
        """Perform one SSDP search and collect its responses."""
        from async_upnp_client.search import async_search

        source_ip = _default_route_ipv4()
        _LOGGER.debug("SSDP search using default-route IPv4 %s", source_ip)
        _LOGGER.debug(
            "Starting SSDP search: target=%s timeout=%ss",
            self.search_target,
            self.search_timeout,
        )
        discovered: asyncio.Queue[DiscoveryEvent] = asyncio.Queue()

        async def on_response(
            headers: Mapping[str, object],
            destination: asyncio.Queue[DiscoveryEvent] = discovered,
        ) -> None:
            observation = _observation_from_response(headers)
            if observation is not None:
                await destination.put(DiscoveryEvent(DiscoveryState.ADDED, observation))

        await async_search(
            async_callback=on_response,
            source=(source_ip, 0),
            timeout=self.search_timeout,
            search_target=self.search_target,
        )
        await asyncio.sleep(0)
        _LOGGER.debug("SSDP search completed with %d response(s)", discovered.qsize())
        return discovered

    async def _wait_for_next_search(self) -> None:
        """Wait for the next polling interval, unless the adapter is stopped."""
        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=max(0.0, self.search_interval - self.search_timeout),
            )
        except TimeoutError:
            pass

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        """Yield SSDP responses collected during successive searches."""
        if not self._running:
            raise RuntimeError("SSDPPlugin.start() must be called before discover()")

        while self._running:
            discovered = await self._search()
            while not discovered.empty():
                yield discovered.get_nowait()

            await self._wait_for_next_search()

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
