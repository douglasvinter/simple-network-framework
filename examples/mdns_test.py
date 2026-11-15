import asyncio

from snf import DiscoveryEngine
from snf.adapters.mdns import MDNSPlugin, ALL_MDSNS_SERVICE_TYPES


async def main():
    plugin = MDNSPlugin(
        service_types=ALL_MDSNS_SERVICE_TYPES,
        resolve_timeout=5000,
    )

    async with DiscoveryEngine([plugin]) as discovery:
        async for service in discovery.discover():
            print(
                f"[{service.protocol}] {service.name} "
                f"{service.address}:{service.port}"
            )

if __name__ == "__main__":
    asyncio.run(main())