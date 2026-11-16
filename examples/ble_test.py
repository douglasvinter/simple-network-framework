"""Discover Bluetooth Low Energy advertisements (no pairing or connection)."""

import asyncio
import logging

from snf import DiscoveryEngine, InMemoryStorage
from snf.adapters.ble import BLEPlugin

_LOGGER = logging.getLogger("examples.ble")


async def main() -> None:
    plugin = BLEPlugin(
        device_timeout=15.0,
        rssi_update_threshold=5,
    )

    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as discovery:
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("snf").setLevel(logging.DEBUG)
    asyncio.run(main())
