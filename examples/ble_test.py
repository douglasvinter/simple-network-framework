"""Discover Bluetooth Low Energy advertisements (no pairing or connection)."""

import asyncio
import logging

from snf import DiscoveryEngine
from snf.adapters.ble import BLEPlugin

_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    plugin = BLEPlugin(
        device_timeout=15.0,
        rssi_update_threshold=5,
    )

    async with DiscoveryEngine([plugin]) as discovery:
        async for event in discovery.discover():
            device = event.device
            _LOGGER.info(
                "[%s] [%s] %s (%s) rssi=%s services=%s",
                event.state.value,
                device.protocol,
                device.name,
                device.identifier,
                device.metadata.get("rssi"),
                device.metadata.get("service_uuids"),
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
