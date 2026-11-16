"""Discover SLP services using OpenSLP's slptool executable."""

import asyncio
import logging

from snf import DiscoveryEngine
from snf.adapters.slp import SLPPlugin

_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    # Requires OpenSLP's slptool executable on PATH.
    # Set service_types=["service:printer"] to restrict discovery.
    plugin = SLPPlugin(
        service_types=None,
        interval=60.0,
        command_timeout=15.0,
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
