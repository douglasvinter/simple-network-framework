"""Run all installed discovery plugins and log discovered devices."""

import asyncio
import logging

from snf import DiscoveryEngine, InMemoryStorage, create_plugins

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("snf-debug.log", encoding="utf-8")],
)
logging.getLogger("snf").setLevel(logging.DEBUG)

_LOGGER = logging.getLogger("examples.discover_all")


async def main() -> None:
    selected = create_plugins()

    _LOGGER.info("Starting discovery with plugins: %s", [p.name for p in selected])

    async with DiscoveryEngine(selected, storage=InMemoryStorage()) as discovery:
        async for event in discovery.discover():
            device = event.observation
            endpoints = ", ".join(
                f"{endpoint.transport}://{endpoint.address}"
                + (f":{endpoint.port}" if endpoint.port is not None else "")
                for endpoint in device.endpoints
            )
            _LOGGER.info(
                "[%s] [%s] %s (%s) %s",
                event.state.value,
                device.protocol,
                device.name,
                device.identifier,
                endpoints,
            )


if __name__ == "__main__":
    asyncio.run(main())
