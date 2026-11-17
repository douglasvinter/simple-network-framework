"""Discover SLP services using OpenSLP's slptool executable."""

import asyncio
import logging

from snf import DiscoveryEngine, InMemoryStorage
from snf.adapters.slp import SLPPlugin

_LOGGER = logging.getLogger("examples.slp")


async def main() -> None:
    # Requires OpenSLP's slptool executable on PATH.
    # Set service_types=["service:printer"] to restrict discovery.
    plugin = SLPPlugin(
        service_types=None,
        interval=60.0,
        command_timeout=15.0,
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
    )
    logging.getLogger("snf").setLevel(logging.DEBUG)
    asyncio.run(main())
