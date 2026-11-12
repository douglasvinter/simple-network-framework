"""Discover UPnP, DNS-SD, and (when installed) SLP services."""

import asyncio
import shutil

from snf import DiscoveryEngine, load_plugins


async def main() -> None:
    available = load_plugins()
    selected = [
        available[name]()
        for name in ("ssdp", "mdns")
        if name in available
    ]
    if "slp" in available and shutil.which("slptool"):
        selected.append(available["slp"]())

    async with DiscoveryEngine(selected) as discovery:
        async for service in discovery.discover():
            print(
                f"[{service.protocol}] {service.name} "
                f"{service.address}:{service.port or '-'} "
                f"({service.service_type or 'unknown type'})"
            )


if __name__ == "__main__":
    asyncio.run(main())
