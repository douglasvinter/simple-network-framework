"""Discover mDNS/DNS-SD services using the SNF discovery engine."""

import asyncio
import logging

from snf import DiscoveryEngine
from snf.adapters.mdns import DEFAULT_SERVICE_TYPES, MDNSPlugin

_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    plugin = MDNSPlugin(
        service_types=DEFAULT_SERVICE_TYPES,
        resolve_timeout=5000,
    )

    async with DiscoveryEngine([plugin]) as discovery:
        async for event in discovery.discover():
            device = event.device
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
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
