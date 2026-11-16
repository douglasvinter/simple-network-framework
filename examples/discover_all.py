"""Run the installed network discovery plugins and log discovered devices."""

import asyncio
import logging

from snf import DiscoveryEngine, load_plugins

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("snf").setLevel(logging.DEBUG)

_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    available = load_plugins()
    selected = []
    for name in ("ssdp", "mdns"):
        plugin_type = available.get(name)
        if plugin_type is None:
            continue
        try:
            selected.append(plugin_type())
        except Exception:
            _LOGGER.exception("Failed to initialize discovery plugin %r", name)

    _LOGGER.info("Starting discovery with plugins: %s", [p.name for p in selected])

    async with DiscoveryEngine(selected) as discovery:
        async for event in discovery.discover():
            device = event.device
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
