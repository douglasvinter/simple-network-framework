"""Discover UPnP, DNS-SD, and (when installed) SLP services."""

import asyncio
import logging
import shutil

from snf import DiscoveryEngine, load_plugins

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("snf").setLevel(logging.DEBUG)

_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    available = load_plugins()
    selected = [
        available[name]()
        for name in ("ssdp", "mdns")
        if name in available
    ]
    if "slp" in available and shutil.which("slptool"):
        selected.append(available["slp"]())

    _LOGGER.debug("Selected discovery plugins: %s", [plugin.name for plugin in selected])

    async with DiscoveryEngine(selected) as discovery:
        async for service in discovery.discover():
            print(
                f"[{service.protocol}] {service.name} "
                f"{service.address}:{service.port or '-'} "
                f"({service.service_type or 'unknown type'})"
            )


if __name__ == "__main__":
    asyncio.run(main())
