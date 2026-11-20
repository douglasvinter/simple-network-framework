# Developer Guide

Use SNF from Python or mount its optional REST/SSE adapter. For design details see [Architecture](architecture.md); for planned capabilities see the [ADR](adr-python-first-network-framework.md).

## Install

Python 3.11+ is required.

```bash
python -m pip install -e ".[all,dev]"  # local development: protocols + API + tests
python -m pip install "simple-network-framework[api]"  # HTTP only
```

The `all` extra includes SSDP, mDNS, BLE, FastAPI, SSE, and Uvicorn. Installing HTTP dependencies does not start a server.

## Direct discovery

```python
import asyncio
from snf import DiscoveryEngine, InMemoryStorage, create_plugins


async def main():
    async with DiscoveryEngine(create_plugins(), storage=InMemoryStorage()) as engine:
        async for event in engine.discover():
            print(event.state.value, event.observation.name)
            print(engine.snapshot(protocol="mdns"))


asyncio.run(main())
```

`create_plugins()` loads installed entry-point plugins and skips construction failures by default. `DiscoveryEngine` also skips failed plugin starts by default; use `strict=True` to fail startup. The engine only processes events while `discover()` is consumed.

`engine.snapshot(protocol=None)` and `engine.get_observation(protocol, identifier)` read the current registry. `await engine.saved_observations(protocol=None)` reads remembered storage. The registry deduplicates unchanged observations and is bounded (default 4,096 entries); eviction does not emit `REMOVED`.

## Background discovery

```python
from snf import NetworkRuntime

async with NetworkRuntime() as network:
    print(network.snapshot())
    print(network.observation_map(protocol="mdns"))
    subscription = network.subscribe(protocol="mdns")
    try:
        async for event in subscription:
            print(event.state.value, event.observation.identifier)
    finally:
        subscription.close()
```

The runtime consumes discovery in one background task. Subscribers receive future-only events, with bounded buffers and no replay. Slow subscribers are disconnected. Constructor options include `plugins`, `storage`, `subscriber_buffer_size=128`, and `strict=False`.

## Run the HTTP API

From the repository root:

```bash
python -m pip install -e ".[all,dev]"
python -m uvicorn examples.run_api:app --host 127.0.0.1 --port 8000
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- Live observations: `GET /network/discoveries?protocol=mdns`
- Grouped observations: `GET /network/discoveries/map`
- Future-only SSE: `GET /network/discoveries/events` (try `curl -N`)
- Health: `GET /network/health` (includes UTC timestamp and `discovery_running`)

The example mounts `create_router(network)` in FastAPI and manages the shared runtime through application lifespan. Health indicates consumer task status, not per-plugin readiness. Bind localhost unless the application supplies appropriate access controls.

**The map is not a unique-device inventory.** Records are keyed by protocol and identifier. The same TV may appear under several SSDP and mDNS advertisements; BLE addresses can rotate. SSDP response-source ports are not necessarily the advertised service ports. Use `metadata.location` only as untrusted discovery evidence; inspection and entity correlation are deferred.

## Custom discovery plugins

Implement `DiscoveryPlugin` with a unique `name`, async `start()` and `stop()`, and `discover()` returning `AsyncIterator[DiscoveryEvent]`:

```python
from collections.abc import AsyncIterator
from snf import DiscoveryEvent, DiscoveryObservation, DiscoveryState


class ExamplePlugin:
    name = "example"

    async def start(self) -> None:
        pass

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        yield DiscoveryEvent(
            DiscoveryState.ADDED,
            DiscoveryObservation(protocol=self.name, identifier="device-1", name="Demo"),
        )

    async def stop(self) -> None:
        pass
```

Register the class in your distribution's `pyproject.toml`:

```toml
[project.entry-points."snf.protocols"]
example = "my_plugin:ExamplePlugin"
```

Plugins own their protocol resources and must clean up on partial startup, cancellation, and shutdown. Do not block the event loop or perform device control during discovery. For a full implementation, see [Custom Protocol Adapter](protocol-plugin-example.md).

## Storage and logging

Inject an `ObservationStorage` implementation with async `get`, `upsert`, `remove`, and `snapshot` methods, keyed by `(protocol, identifier)`. `InMemoryStorage` is the non-durable reference driver. ADDED/UPDATED observations are saved; REMOVED does not erase remembered records. Storage failures propagate; the application owns retries and driver lifecycle.

SNF uses the standard `snf` logger namespace; the application configures handlers. See [Logging](logging.md) and [Async Discovery Lifecycle](async-discovery-lifecycle.md).
