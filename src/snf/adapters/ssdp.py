"""SSDP adapter backed by async-upnp-client."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from importlib.util import find_spec

from snf.models import Service


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
                "Install SSDP support with: "
                "pip install 'simple-network-framework[ssdp]'"
            )
        self.search_target = search_target
        self.search_interval = search_interval
        self.search_timeout = search_timeout
        self._running = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._running = True
        self._stop_event.clear()

    async def discover(self) -> AsyncIterator[Service]:
        if not self._running:
            raise RuntimeError("SSDPPlugin.start() must be called before discover()")

        from async_upnp_client.search import async_search

        while self._running:
            discovered: asyncio.Queue[Service] = asyncio.Queue()

            async def on_response(headers: object) -> None:
                values = {str(key).lower(): value for key, value in dict(headers).items()}
                host = str(values.get("_host", ""))
                if not host:
                    return
                raw_port = values.get("_port")
                port = int(raw_port) if raw_port is not None else None
                usn = str(values.get("usn", ""))
                location = values.get("location")
                await discovered.put(
                    Service(
                        protocol=self.name,
                        name=usn or str(location or host),
                        address=host,
                        port=port,
                        service_type=str(values.get("st", "")) or None,
                        metadata=values,
                    )
                )

            await async_search(
                async_callback=on_response,
                timeout=self.search_timeout,
                search_target=self.search_target,
            )
            # async-upnp-client schedules async callbacks as tasks; give them a
            # turn to enqueue their already-received responses before draining.
            await asyncio.sleep(0)
            while not discovered.empty():
                yield discovered.get_nowait()

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=max(0.0, self.search_interval - self.search_timeout),
                )
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
