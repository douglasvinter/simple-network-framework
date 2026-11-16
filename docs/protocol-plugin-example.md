# Implementing a Custom Protocol Adapter

This guide walks through a complete third-party discovery plugin. The example uses a small UDP beacon protocol so that the adapter lifecycle, event translation, packaging, and testing are visible without depending on a real vendor SDK.

The beacon format below is illustrative; it is not an existing industry protocol. Replace its socket handling and message parser with the transport and protocol library used by the protocol you are implementing.

For the overall application lifecycle and plugin contract, see the [Developer Guide](developer-guide.md#6-implement-a-custom-discovery-plugin).

## 1. Understand the adapter boundary

A protocol adapter is responsible for translating protocol-specific observations into SNF's protocol-neutral models:

| Protocol concern | SNF representation |
| --- | --- |
| Protocol name | `Device.protocol` |
| Stable identifier within that protocol | `Device.identifier` |
| Human-readable advertised name | `Device.name` |
| Address and transport used to reach the device/service | `Endpoint` |
| Advertised protocol service | `Service` |
| First observation, changed observation, disappearance | `DiscoveryEvent` with `ADDED`, `UPDATED`, or `REMOVED` |

The registry identifies a record by the pair `(protocol, identifier)`. Choose an identifier that is stable for the protocol, not a display name or an IP address that may change.

An adapter should observe and report. It should not pair with devices, connect to them for control, or execute device actions. Those belong in an application or a separate control layer.

## 2. Create a plugin package

A third-party plugin is a normal Python package. One possible layout is:

```text
snf-example-plugin/
├── pyproject.toml
└── src/
    └── snf_example_plugin/
        └── __init__.py
```

The example uses only Python's standard library, so it does not need a protocol-specific runtime dependency.

## 3. Define the example wire protocol

For this walkthrough, a device sends a UDP datagram to the listener using one of these messages:

```text
DISCOVERED|<identifier>|<name>|<service-port>
REMOVED|<identifier>|<name>|<service-port>
```

For example:

```text
DISCOVERED|device-001|Living Room Sensor|5683
REMOVED|device-001|Living Room Sensor|5683
```

The UDP sender's IP address is used as the device host address. The advertised service port becomes the endpoint port.

A real protocol may use binary frames, multicast, broadcasts, a vendor SDK, or callbacks from another library. Only the transport and parsing portions should change; the SNF event translation and plugin lifecycle remain the same.

## 4. Implement the adapter

Create `src/snf_example_plugin/__init__.py`:

```python
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from snf.models import (
    Device,
    DiscoveryEvent,
    DiscoveryState,
    Endpoint,
    Service,
)

_LOGGER = logging.getLogger(__name__)


class _BeaconProtocol(asyncio.DatagramProtocol):
    """Forward received UDP datagrams to the plugin."""

    def __init__(self, plugin: ExampleBeaconPlugin) -> None:
        self._plugin = plugin

    def datagram_received(
        self, data: bytes, addr: tuple[str, int]
    ) -> None:
        self._plugin._handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.warning("UDP beacon socket reported an error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc is not None:
            _LOGGER.warning("UDP beacon socket closed with an error: %s", exc)


class ExampleBeaconPlugin:
    """Discover devices that announce themselves using the example UDP beacon."""

    name = "example-beacon"

    def __init__(
        self,
        *,
        listen_host: str = "0.0.0.0",
        listen_port: int = 19001,
    ) -> None:
        if not 0 <= listen_port <= 65535:
            raise ValueError("listen_port must be between 0 and 65535")

        self.listen_host = listen_host
        self.listen_port = listen_port
        self._events: asyncio.Queue[DiscoveryEvent | None] = asyncio.Queue()
        self._transport: asyncio.DatagramTransport | None = None

    async def start(self) -> None:
        """Bind the UDP listener before the engine starts consuming events."""
        if self._transport is not None:
            raise RuntimeError("ExampleBeaconPlugin is already running")

        self._events = asyncio.Queue()
        loop = asyncio.get_running_loop()
        transport, _protocol = await loop.create_datagram_endpoint(
            lambda: _BeaconProtocol(self),
            local_addr=(self.listen_host, self.listen_port),
        )
        self._transport = transport

        _LOGGER.info(
            "Listening for example beacons on %s:%d",
            self.listen_host,
            self.listen_port,
        )

    def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        """Parse one protocol message and translate it into an SNF event."""
        try:
            message = data.decode("utf-8").strip()
            action, identifier, name, port_text = message.split("|", maxsplit=3)
            service_port = int(port_text)
            if not identifier or not name or not 1 <= service_port <= 65535:
                raise ValueError("invalid identifier, name, or service port")
            if action not in {"DISCOVERED", "REMOVED"}:
                raise ValueError(f"unsupported action: {action}")
        except (UnicodeDecodeError, ValueError) as exc:
            _LOGGER.debug("Ignoring malformed beacon from %s: %s", addr, exc)
            return

        endpoint = Endpoint(
            transport="udp",
            address=addr[0],
            port=service_port,
        )
        service = Service(
            name=name,
            service_type="example-beacon",
            endpoints=(endpoint,),
        )
        device = Device(
            protocol=self.name,
            identifier=identifier,
            name=name,
            endpoints=(endpoint,),
            services=(service,),
            metadata={"source_address": addr[0]},
        )

        state = (
            DiscoveryState.ADDED
            if action == "DISCOVERED"
            else DiscoveryState.REMOVED
        )
        self._events.put_nowait(DiscoveryEvent(state, device))

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        """Yield translated events until stop() closes the event stream."""
        if self._transport is None:
            raise RuntimeError("ExampleBeaconPlugin.start() must be called first")

        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def stop(self) -> None:
        """Close the socket and unblock a discover() waiting for its next event."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None

        self._events.put_nowait(None)
```

### Lifecycle responsibilities

- `start()` allocates the socket and any protocol-specific resources. It must finish initialization before discovery begins.
- The protocol callback parses incoming data and places normalized events on an asyncio queue. It does not block the event loop.
- `discover()` is an async generator that waits for events and yields them to the engine. It is expected to remain active while the plugin is running.
- `stop()` releases resources and unblocks the generator. It must also be safe when startup only partially completed.

The queue is the boundary between callback-based libraries and SNF's async iterator contract. For a protocol library that already exposes an async iterator, the adapter can often yield translated events directly without a queue.

### Important: removal semantics

This sample emits `REMOVED` only when the protocol explicitly sends a removal message. If a real protocol has no removal message, do not invent one from a single missed packet. Implement a protocol-appropriate lease/timeout policy, and document the evidence and timing used to expire an observation.

Similarly, emit `UPDATED` when the protocol reports changed data for an already-known identifier. The engine's registry normalizes repeated events and suppresses unchanged records, but adapters should still avoid generating unnecessary traffic where practical.

## 5. Register the plugin with Python entry points

Create the plugin package's `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "snf-example-plugin"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["simple-network-framework>=0.2.0a1"]

[project.entry-points."snf.protocols"]
example-beacon = "snf_example_plugin:ExampleBeaconPlugin"

[tool.hatch.build.targets.wheel]
packages = ["src/snf_example_plugin"]
```

The entry-point group must be exactly `snf.protocols`. Its key is the plugin's discovery name in the mapping returned by `load_plugins()`; its value is the import path to the plugin class.

Install SNF and the plugin into the same environment:

```bash
python -m pip install -e ../simple-network-framework
python -m pip install -e .
```

If you change entry-point metadata during development, reinstall the plugin package so the environment's distribution metadata is refreshed.

## 6. Load and run the plugin

A consuming application uses the same engine as it does for built-in adapters:

```python
import asyncio
import logging

from snf import DiscoveryEngine, load_plugins

_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    available = load_plugins()
    plugin_class = available["example-beacon"]
    plugin = plugin_class(listen_host="0.0.0.0", listen_port=19001)

    async with DiscoveryEngine([plugin]) as engine:
        async for event in engine.discover():
            _LOGGER.info(
                "%s: %s (%s)",
                event.state.value,
                event.device.name,
                event.device.identifier,
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

The application does not need to know about UDP datagrams or the plugin's parser. It only sees SNF domain models and lifecycle events.

For applications that load several optional plugins, initialize each one independently and log failures, as shown in the [Developer Guide](developer-guide.md#3-run-discovery).

## 7. Test the protocol translation

Keep protocol parsing tests independent of live network I/O. For this example, the parser can be tested directly:

```python
import asyncio

from snf.models import DiscoveryState
from snf_example_plugin import ExampleBeaconPlugin


def test_discovered_beacon_is_translated_to_snf_event():
    plugin = ExampleBeaconPlugin()
    plugin._events = asyncio.Queue()

    plugin._handle_datagram(
        b"DISCOVERED|device-001|Living Room Sensor|5683",
        ("192.0.2.25", 42000),
    )

    event = plugin._events.get_nowait()

    assert event.state is DiscoveryState.ADDED
    assert event.device.protocol == "example-beacon"
    assert event.device.identifier == "device-001"
    assert event.device.name == "Living Room Sensor"
    assert event.device.endpoints[0].address == "192.0.2.25"
    assert event.device.endpoints[0].port == 5683


def test_malformed_beacon_is_ignored():
    plugin = ExampleBeaconPlugin()
    plugin._events = asyncio.Queue()

    plugin._handle_datagram(b"not-a-valid-beacon", ("192.0.2.25", 42000))

    assert plugin._events.empty()
```

Also test the plugin lifecycle and integration with `DiscoveryEngine`:

- Startup binds the expected interface and port.
- Incoming protocol messages produce the expected SNF events.
- Invalid or unexpected messages are ignored or logged without crashing discovery.
- Repeated observations use the same protocol-scoped identifier.
- Changed observations produce updates; explicit or policy-based disappearance produces removals.
- Shutdown closes the socket and unblocks a pending discovery iterator.
- Startup and shutdown failures do not leak sockets, tasks, callbacks, or subprocesses.

Use mocks/fakes for protocol-library boundaries in deterministic tests. Keep tests that require actual devices, network interfaces, or multicast behavior in a separate integration-test group.

## 8. Implementation checklist

Before publishing a protocol plugin, verify:

- [ ] The plugin implements `name`, `start()`, `discover()`, and `stop()`.
- [ ] Protocol-specific messages are translated into `Device`, `Service`, `Endpoint`, and `DiscoveryEvent`.
- [ ] The protocol identifier is stable and scoped to the plugin's `name`.
- [ ] `REMOVED` events are based on defensible protocol evidence or a documented expiry policy.
- [ ] Blocking I/O does not run on the event loop.
- [ ] All sockets, tasks, subprocesses, scanners, and callbacks are released on shutdown.
- [ ] The package registers its class in the `snf.protocols` entry-point group.
- [ ] Unit tests cover parsing and event translation; integration tests cover the engine boundary.

A discovery plugin extends SNF's ability to observe devices. It does not need to add persistence, device control, pairing, or home-automation behavior to the framework.
