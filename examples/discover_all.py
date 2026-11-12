"""Discover UPnP and DNS-SD services on the local network."""

import asyncio

from snf import DiscoveryEngine, load_plugins


async def main() -> None:
    available = load_plugins()
    selected = [available[name]() for name in ("ssdp", "mdns") if name in available]
    async with DiscoveryEngine(selected) as discovery:
        async for service in discovery.discover():
            print(f"[{service.protocol}] {service.name} {service.address}:{service.port or '-'}")


if __name__ == "__main__":
    asyncio.run(main())
