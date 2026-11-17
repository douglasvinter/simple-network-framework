"""Discover SSDP/UPnP devices using the SNF discovery engine."""

import asyncio
import logging

from snf import DiscoveryEngine, InMemoryStorage
from snf.adapters.ssdp import SSDPPlugin

_LOGGER = logging.getLogger("examples.ssdp")


async def main() -> None:
    plugin = SSDPPlugin(
        search_target="ssdp:all",
        search_interval=30.0,
        search_timeout=5,
    )

    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as discovery:
        async for event in discovery.discover():
            device = event.observation
            _LOGGER.info(
                "[%s] [%s] %s (%s) endpoints=%s services=%s",
                event.state.value,
                device.protocol,
                device.name,
                device.identifier,
                device.endpoints,
                device.services,
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("snf-debug.log", encoding="utf-8")],
    )
    logging.getLogger("snf").setLevel(logging.DEBUG)
    asyncio.run(main())
