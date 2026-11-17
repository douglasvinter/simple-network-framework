# Developer Guide

This guide explains how to use Simple Network Framework (SNF) from an application, run its optional HTTP API, and implement and distribute a third-party discovery plugin. See [Architecture](architecture.md) for the current implementation and the [ADR](adr-python-first-network-framework.md) for planned capabilities.

## 1. Install SNF

SNF requires Python 3.11 or newer. Protocol backends are optional dependencies.

Install all Python protocol backends and the optional HTTP API:

```bash
python -m pip install 'simple-network-framework[all]'
```

For a smaller installation, select only the protocols you need:

```bash
python -m pip install 'simple-network-framework[ssdp,mdns]'
python -m pip install 'simple-network-framework[ble]'
```

SLP has an additional native dependency: install OpenSLP and ensure its `slptool` executable is available on `PATH`.

For local development from a clone:

```bash
python -m pip install -e '.[all,dev]'
```

## 2. Discover available plugins

SNF uses Python package entry points in the `snf.protocols` group.

```python
import logging

from snf import load_plugins

logger = logging.getLogger(__name__)
available = load_plugins()

for name, plugin_class in available.items():
    logger.info("Loaded plugin %s: %s", name, plugin_class)
```

The returned dictionary maps the entry-point name to the plugin class. Loading the entry point imports the class, but does not instantiate or start it.

A plugin may be absent because its distribution is not installed or because it has not registered the expected entry point. If importing a registered plugin fails (including a missing module-level dependency), the loader logs the exception and continues loading other plugins. Optional backend packages must also be installed before the corresponding adapter can be instantiated.

## 3. Run discovery

The common application flow is:

1. Load the plugins you want.
2. Instantiate them.
3. Pass the instances to `DiscoveryEngine`.
4. Enter the engine's asynchronous context.
5. Consume `engine.discover()` with `async for`.
6. Read the current inventory through `engine.observations` or `engine.get_observation()`.

```python
import asyncio
import logging

from snf import DiscoveryEngine, InMemoryStorage, create_plugins

logger = logging.getLogger(__name__)


async def main() -> None:
    selected = create_plugins()

    async with DiscoveryEngine(selected, storage=InMemoryStorage()) as engine:
        async for event in engine.discover():
            device = event.observation
            logger.info(
                "%s %s %s %s %s",
                event.state.value,
                device.protocol,
                device.name,
                device.identifier,
                device.endpoints,
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

The example above uses the adapters that are installed and registered. It does not automatically include SLP. To use SLP, install OpenSLP, ensure `slptool` is on `PATH`, and instantiate its registered plugin.

By default, `create_plugins()` logs and skips plugins that fail construction, and `DiscoveryEngine` logs, cleans up, and skips plugins that fail `start()`. To require all selected plugins, use `create_plugins(strict=True)` and `DiscoveryEngine(selected, storage=InMemoryStorage(), strict=True)`. Strict startup still cleans up successfully started plugins before raising.

The async context starts the plugins and guarantees that the engine's shutdown path runs when the context exits. The discovery iterator is intended to run until the plugin streams finish or the consumer cancels/exits the context.

See [Logging](logging.md) for routing SNF logs into your application's handlers.

## 4. Consume events and query inventory

An event has a `state` and a `device`.

```python
async with DiscoveryEngine(selected, storage=InMemoryStorage()) as engine:
    async for event in engine.discover():
        device = event.observation

        logger.info(
            "%s observation: %s",
            event.state.value,
            device.name,
        )

        # Current inventory snapshot, not a historical event list.
        current_devices = engine.observations

        # Filter a point-in-time snapshot by protocol.
        mdns_devices = engine.snapshot(protocol="mdns")

        # Identifiers are scoped to the protocol.
        current = engine.get_observation(device.protocol, device.identifier)
```

The public API also exposes the domain models:

- `DiscoveryObservation`
- `Service`
- `Endpoint`
- `DiscoveryEvent`
- `DiscoveryState`

The `ObservationRegistry` class is public, but most applications should use the inventory managed by `DiscoveryEngine`.

Use `engine.snapshot()` for all devices or `engine.snapshot(protocol="ble")` for one protocol. Both return immutable tuples representing the inventory at the moment of the call; they do not trigger discovery or wait for new devices. `engine.observations` remains an alias for the unfiltered snapshot. An unknown protocol returns an empty tuple. Snapshots only reflect events already consumed through `engine.discover()`.

### Understand the event states

- `ADDED`: the registry did not have this protocol/identifier before.
- `UPDATED`: the registry already had the device and its observed data changed.
- No event: the observation is identical to the current record and is suppressed.
- `REMOVED`: the registry had the device and the adapter reported it removed.

The registry can normalize an adapter's incoming event. For example, an adapter may yield `ADDED` more than once; the consumer receives `UPDATED` if the known device changed, or no event if it did not.

The inventory is bounded to 4,096 records by default. You can override that limit:

```python
engine = DiscoveryEngine(selected, storage=InMemoryStorage(), dedupe_cache_size=8192)
```

The parameter controls the registry's maximum number of entries. When the limit is exceeded, the oldest entry is evicted. Eviction currently does not produce a `REMOVED` event.

## 5. Configure built-in adapters

Adapters expose protocol-specific constructor arguments. Use the class documentation and source as the definitive reference for the installed version.

Examples:

```python
from snf.adapters.ssdp import SSDPPlugin
from snf.adapters.mdns import MDNSPlugin
from snf.adapters.ble import BLEPlugin
from snf.adapters.slp import SLPPlugin

ssdp = SSDPPlugin(
    search_target="ssdp:all",
    search_interval=30.0,
    search_timeout=5,
)

mdns = MDNSPlugin(
    service_types=["_googlecast._tcp.local.", "_airplay._tcp.local."]
)

ble = BLEPlugin(
    device_timeout=15.0,
    rssi_update_threshold=5,
)

# Requires OpenSLP's slptool executable on PATH.
slp = SLPPlugin(interval=60.0)
```

Adapters validate their optional backends during initialization and raise an actionable installation error when a dependency is missing. Use `create_plugins()` for framework-managed initialization failure isolation. Applications that need custom adapter arguments can instantiate selected classes explicitly.

### What BLE discovery provides

BLE discovery reads advertisements. Depending on what a peripheral advertises, a device record may include:

- BLE address and advertised name.
- RSSI and transmit power.
- Advertised service UUIDs.
- Manufacturer-specific data.
- Service data.

BLE scanning does not pair with peripherals, connect to them, or enumerate their GATT services and characteristics.

## 6. Implement a custom discovery plugin

A plugin implements the `DiscoveryPlugin` protocol:

```python
from collections.abc import AsyncIterator

from snf.models import (
    DiscoveryObservation,
    DiscoveryEvent,
    DiscoveryState,
    Endpoint,
)


class ExamplePlugin:
    name = "example"

    async def start(self) -> None:
        """Allocate resources and start observing the protocol."""
        ...

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        """Yield normalized device lifecycle events."""
        device = DiscoveryObservation(
            protocol=self.name,
            identifier="example-device-001",
            name="Example device",
            endpoints=(Endpoint("ip", "192.0.2.10", 1234),),
        )
        yield DiscoveryEvent(DiscoveryState.ADDED, device)

    async def stop(self) -> None:
        """Stop observation and release resources."""
        ...
```

The example above illustrates the event shape. A production plugin should normally keep observing until stopped, yielding events as observations arrive. Its `start()` method should allocate the resources needed by discovery, and `stop()` must release them.

The contract in `snf.plugins.DiscoveryPlugin` is:

```python
class DiscoveryPlugin(Protocol):
    name: str

    async def start(self) -> None: ...

    def discover(self) -> AsyncIterator[DiscoveryEvent]: ...

    async def stop(self) -> None: ...
```

An async-generator method declared with `async def` satisfies the iterator behavior: calling it returns an async iterator that the engine consumes with `async for`.

### Plugin implementation guidelines

1. **Use a stable protocol namespace.** Set `name` to a unique, lowercase protocol identifier.
2. **Normalize at the adapter boundary.** Translate protocol-specific objects into `DiscoveryObservation`, `Service`, `Endpoint`, and `DiscoveryEvent`.
3. **Use protocol-scoped identifiers.** The registry key is `(device.protocol, device.identifier)`.
4. **Emit meaningful lifecycle events.** Emit `REMOVED` only when your protocol-specific discovery logic has enough evidence that the observation should leave the inventory.
5. **Avoid noisy updates.** Do not emit an update for unchanged data. The registry suppresses exact duplicate device records, but adapter-side filtering can reduce queue traffic.
6. **Keep blocking work off the event loop.** Use an async library or an appropriate executor for blocking I/O.
7. **Own your resources.** Close sockets, browsers, subprocesses, scanners, callback registrations, and background tasks in `stop()`.
8. **Make shutdown reliable.** `stop()` should tolerate partially initialized state and should unblock a discovery iterator that is waiting for input.
9. **Do not control devices from a discovery plugin.** Pairing, connecting, and invoking device operations belong to a separate consumer/control layer.
10. **Treat network data as untrusted.** Discovery does not imply that an endpoint is reachable or safe to contact.

For a complete, runnable adapter example—including a UDP listener, protocol parsing, event translation, packaging, and tests—see [Implementing a Custom Protocol Adapter](protocol-plugin-example.md).\n\n## 7. Register and distribute the plugin

A third-party plugin should be packaged as a normal Python distribution and declare an entry point in its `pyproject.toml`.

For example:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "snf-example-plugin"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["simple-network-framework>=0.2"]

[project.entry-points."snf.protocols"]
example = "snf_example_plugin:ExamplePlugin"
```

The value on the right side is the import path to the plugin class. The entry-point name (`example`) is the name returned by `load_plugins()`.

Install the plugin distribution into the same Python environment as SNF:

```bash
python -m pip install -e .
```

Then load it:

```python
from snf import load_plugins

plugins = load_plugins()
example_plugin = plugins["example"]()
```

If you add or change entry points while developing an editable package, reinstall the package so its installed distribution metadata is refreshed.

## 8. Testing a plugin

At minimum, test:

- The plugin can be instantiated with valid configuration.
- `start()` initializes the required resources.
- `discover()` yields valid `DiscoveryEvent` instances.
- The device's protocol and identifier remain stable across repeated observations.
- Updates and removals are represented correctly.
- Duplicate observations do not create noisy inventory events.
- `stop()` releases resources and unblocks pending discovery.
- Partial startup failure does not leak resources.

Test normalization separately from live network I/O. Use fakes or mocks for protocol-library callbacks and responses. Keep hardware/network integration tests separate because they depend on the local environment.

## 9. Logging

SNF uses Python's standard `logging` module. Configure logging in the consuming application:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("snf").setLevel(logging.DEBUG)
```

Use DEBUG logs to inspect plugin pumps and protocol activity. INFO is generally more appropriate for normal application operation.

## 10. Inventory storage and application boundaries

The `DiscoveryEngine` constructor requires a keyword-only `storage` argument. SNF supplies the `InMemoryStorage` reference driver but no database implementation.

```python
from snf import DiscoveryEngine, InMemoryStorage, create_plugins

storage = InMemoryStorage()

async with DiscoveryEngine(create_plugins(), storage=storage) as engine:
    async for event in engine.discover():
        live = engine.snapshot(protocol="mdns")
        remembered = await engine.saved_observations(protocol="mdns")
```

### Storage contract and custom implementations

`ObservationStorage` is a structural `Protocol` with asynchronous key/value operations. Records are keyed by `(protocol, identifier)` to avoid collisions across discovery protocols:

```python
from snf import DiscoveryObservation, ObservationStorage

class MyStorage(ObservationStorage):
    async def get(self, protocol: str, identifier: str) -> DiscoveryObservation | None: ...
    async def upsert(self, device: DiscoveryObservation) -> None: ...
    async def remove(self, protocol: str, identifier: str) -> None: ...
    async def snapshot(
        self, *, protocol: str | None = None
    ) -> tuple[DiscoveryObservation, ...]: ...

storage: ObservationStorage = MyStorage()
```

Explicit inheritance is optional for third-party implementations because `Protocol` supports structural typing. The bundled `InMemoryStorage` explicitly inherits `ObservationStorage`. A custom driver may implement its own persistence mechanism without changing SNF.

### Live versus remembered devices

`engine.observations`, `engine.snapshot()`, and `engine.get_observation()` read the bounded, synchronous live `ObservationRegistry`. `await engine.saved_observations(protocol=None)` reads the injected storage, including records from previous sessions when supported by the driver.

The engine awaits `storage.upsert(device)` after normalized `ADDED` and `UPDATED` events, before yielding those events. Duplicate observations are suppressed and not written. A `REMOVED` event clears the live registry record but **does not delete** the remembered record. To forget a device explicitly, call `await storage.remove(protocol, identifier)`. Previously saved devices are not automatically considered online when an engine starts.

Storage exceptions propagate to the consumer; retry, buffering, and recovery policies belong to the storage driver. A failed write occurs after the live registry is updated, so replay of identical observations is not guaranteed. The caller owns initialization and cleanup of any resources used by its storage driver. Reusing one `InMemoryStorage` instance across engines retains its records while that instance exists, but not across process restarts.

Pairing and generic protocol-level interaction are not implemented yet; vendor-specific device behavior and automation remain application responsibilities.
\n## 11. Background discovery runtime (Python-first)\n\nFor long-lived applications, `NetworkRuntime` starts one background consumer when its async context is entered. Unlike direct `DiscoveryEngine.discover()` iteration, inventory updates do not depend on an application actively iterating events.\n\n```python\nimport asyncio\nfrom snf import NetworkRuntime\n\nasync def main():\n    async with NetworkRuntime() as network:\n        print(network.snapshot(protocol=None))\n        print(network.observation_map())\n        subscription = network.subscribe(protocol=None)\n        try:\n            async for event in subscription:\n                print(event.state, event.observation.identifier)\n        finally:\n            subscription.close()\n\nasyncio.run(main())\n```\n\nSupply explicit plugins or an `ObservationStorage` instance when required: `NetworkRuntime(plugins, storage=storage, subscriber_buffer_size=128, strict=False)`. With no plugins argument, installed plugins are created automatically. Unknown protocol filters raise `ValueError`. Subscribers receive future events, not historical replay. A full subscriber buffer disconnects that subscriber; always close subscriptions when finished. The runtime owns its engine lifecycle and the single consumer task.\n\n## 12. Optional FastAPI REST/SSE adapter\n\nInstall `python -m pip install 'simple-network-framework[api]'` (or `'.[all,api,dev]'` from a checkout). HTTP is optional and never launches a server automatically.\n\n```python\nfrom contextlib import asynccontextmanager\nfrom fastapi import FastAPI\nfrom snf import NetworkRuntime\nfrom snf.api import create_router\n\nnetwork = NetworkRuntime()\n\n@asynccontextmanager\nasync def lifespan(app: FastAPI):\n    async with network:\n        yield\n\napp = FastAPI(lifespan=lifespan)\napp.include_router(create_router(network), prefix='/network')\n```\n\n- `GET /network/discoveries`: current protocol-scoped observations, optionally filtered with `?protocol=mdns`.\n- `GET /network/discoveries/map`: grouped protocol/identifier map, with the same filter.\n- `GET /network/discoveries/events`: future-only SSE events named `added`, `updated`, or `removed`; clients have independent bounded subscriptions.\n- `GET /network/health`: `status`, UTC ISO-8601 `timestamp`, `discovery_running`, `observations`, `protocols`.\n\n`discovery_running` reflects whether the single consumer task is alive; it is not a control flag or a guarantee that every adapter is healthy. The runtime is started/stopped through its async context; no start/stop HTTP endpoints are exposed. Protect network inventory endpoints with application-appropriate access controls and avoid exposing them publicly by default.\n
### Run the bundled API example

The `api` extra installs FastAPI, SSE support and Uvicorn. The `all` extra
includes the same HTTP dependencies plus the protocol backends, so no separate
Uvicorn installation is necessary.

```bash
python -m pip install -e ".[all,dev]"
python -m uvicorn examples.run_api:app --host 127.0.0.1 --port 8000
```

Visit `http://127.0.0.1:8000/docs` for Swagger UI or
`http://127.0.0.1:8000/network/health` for a health check. The example uses
FastAPI lifespan to start and stop the shared `NetworkRuntime`; the server is
never started implicitly by installing or importing SNF.

## 13. Observation map versus resolved entities

`GET /network/discoveries/map` returns the same **raw normalized observations** as the discoveries endpoint, indexed first by protocol and then by protocol-scoped identifier. It is a JSON grouping, **not** a topology diagram or deduplicated physical-device inventory. For example, one TV can appear under mDNS AirPlay and multiple SSDP advertisements; multiple SSDP USNs can represent different advertised services from the same host. Do not merge records solely by IP address, display name, or BLE address. BLE privacy addresses can change, and repeated friendly names do not establish identity.

The SSDP adapter's current endpoint port may reflect the UDP response source port rather than the port in the advertised `LOCATION` URL. Treat `metadata.location` as the advertised description locator and **do not assume** an observation endpoint is an actionable UPnP service endpoint. Resolving UPnP descriptions, validating locators, and constructing service-specific endpoints belong to the planned inspection phase, not this HTTP backport. Never fetch arbitrary discovered URLs without appropriate local-network targeting, redirect, timeout and response-size protections.
