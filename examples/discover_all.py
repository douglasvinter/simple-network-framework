"""Discover IP services and Bluetooth Low Energy peripherals."""

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

    if "ble" in available:
        selected.append(available["ble"]())
    else:
        _LOGGER.warning(
            "BLE plugin is not registered. Reinstall SNF with "
            "'python -m pip install -e ".[ble]"' to refresh entry points "
            "and install the Bleak backend."
        )
    if "slp" in available and shutil.which("slptool"):
        selected.append(available["slp"]())

    _LOGGER.debug("Selected discovery plugins: %s", [plugin.name for plugin in selected])

    async with DiscoveryEngine(selected) as discovery:
        async for event in discovery.discover():
            device = event.device
            endpoints = ", ".join(
                f"{endpoint.transport}://{endpoint.address}"
                + (f":{endpoint.port}" if endpoint.port is not None else "")
                for endpoint in device.endpoints
            )
            print(
                f"[{event.state.value}] [{device.protocol}] {device.name} "
                f"({device.identifier}) {endpoints}"
            )


if __name__ == "__main__":
    asyncio.run(main())
