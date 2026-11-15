"""Run mDNS discovery and print the discovered service inventory."""

import asyncio

from snf import DiscoveryEngine
from snf.adapters.mdns import DEFAULT_SERVICE_TYPES, MDNSPlugin


async def main() -> None:
    plugin = MDNSPlugin(
        service_types=DEFAULT_SERVICE_TYPES,
        resolve_timeout=5000,
    )

    async with DiscoveryEngine([plugin]) as discovery:
        async for event in discovery.discover():
            device = event.device
            print(
                f"[{event.state.value}] [{device.protocol}] "
                f"{device.name} {device.endpoints}"
            )


if __name__ == "__main__":
    asyncio.run(main())
