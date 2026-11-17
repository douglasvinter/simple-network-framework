"""Discover mDNS/DNS-SD services using the SNF discovery engine."""

import asyncio
import logging

from snf import DiscoveryEngine, InMemoryStorage
from snf.adapters.mdns import DEFAULT_SERVICE_TYPES, MDNSPlugin

_LOGGER = logging.getLogger("examples.mdns")


async def main() -> None:
    plugin = MDNSPlugin(
        service_types=DEFAULT_SERVICE_TYPES,
        resolve_timeout=5000,
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
