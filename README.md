# Simple Network Framework

An asyncio-based framework for discovering and maintaining an in-memory inventory
of devices and services on local networks, including Bluetooth Low Energy peripherals.

SNF delegates protocol implementation to established libraries. It provides a
protocol-neutral device model, concurrent discovery lifecycle, event de-duplication,
an in-memory inventory, and an entry-point plugin system.

## Scope

SNF discovers devices and the services/endpoints they advertise. It does not pair
Bluetooth devices, connect to devices, invoke device APIs, control TVs or appliances,
or implement automation workflows. Those responsibilities belong to consuming
applications such as a home-automation project.

Discovery identity is protocol-scoped. If SSDP and mDNS report the same physical TV,
SNF currently keeps separate records. It deliberately does not guess that two
observations represent the same physical device.

## Requirements and installation

- Python 3.11 or newer.
- Network access to the LAN for IP discovery.
- A supported Bluetooth adapter and operating-system Bluetooth stack for BLE discovery.

Install all Python protocol backends:

```bash
python -m pip install -e ".[all]"
```

Install only what you need:

```bash
python -m pip install -e ".[ssdp,mdns,ble]"
```

SLP additionally requires the OpenSLP `slptool` executable on `PATH`.

## Quick start

```python
import asyncio
from snf import DiscoveryEngine, load_plugins


async def main() -> None:
    available = load_plugins()
    selected = [
        available[name]()
        for name in ("ssdp", "mdns", "ble")
        if name in available
    ]

    async with DiscoveryEngine(selected) as discovery:
        async for event in discovery.discover():
            device = event.device
            print(event.state, device.protocol, device.name, device.endpoints)

            # The in-memory inventory can also be queried by consumers.
            current_devices = discovery.devices


asyncio.run(main())
```

The engine starts plugins concurrently and merges their event streams. A consumer
can inspect the current immutable inventory through `engine.devices`, or retrieve
a protocol-scoped record with `engine.get_device(protocol, identifier)`.

## Domain model

- `Device`: a protocol-scoped discovered inventory record.
- `Service`: a service advertised by a device.
- `Endpoint`: a transport-specific locator, such as an IP address/port or BLE address.
- `DiscoveryEvent`: an ADDED, UPDATED, or REMOVED lifecycle event for a device.

BLE records include advertisement information such as RSSI, transmit power,
advertised service UUIDs, manufacturer data, and service data. BLE discovery does
not establish a connection or pair with a peripheral.

BLE devices are considered removed after `device_timeout` seconds without a
received advertisement (15 seconds by default). This is an observation timeout,
not proof that the physical device is powered off or out of range.

## Event de-duplication and inventory

The engine maintains a bounded in-memory registry (4,096 devices by default).
Repeated identical observations are suppressed. Changes to a known device are
emitted as UPDATED. A known REMOVED event clears its inventory record; a later
observation is emitted as ADDED again.

Registry identity is protocol + identifier. The registry does not merge records
across discovery protocols. Consumers should not treat BLE addresses as permanent
hardware identities: addresses may be randomized or rotate for privacy.

## Included adapters

| Adapter | Backend | Discovery data |
| --- | --- | --- |
| SSDP / UPnP | async-upnp-client | UPnP identifiers, services and IP endpoints |
| mDNS / DNS-SD | python-zeroconf | Service instances, TXT metadata and IP endpoints |
| SLPv2 | OpenSLP slptool | SLP service URLs and endpoints |
| Bluetooth LE | Bleak | Peripheral advertisements, RSSI, service UUIDs and manufacturer data |

## Third-party plugins

Register an entry point in your plugin distribution:

```toml
[project.entry-points."snf.protocols"]
my-protocol = "my_snf_plugin:MyProtocolPlugin"
```

A plugin implements async `start()`, async-iterator `discover()`, and async
`stop()` methods. It yields `DiscoveryEvent` objects. The plugin owns its protocol
resources; the engine handles lifecycle, concurrency, aggregation and inventory.

## Development

```bash
python -m pip install -e ".[all,dev]"
python -m pytest
ruff check .
mypy src
```

## Security

Discovery data is untrusted input. SNF does not automatically fetch SSDP LOCATION
URLs, connect to discovered devices, or invoke discovered services. Applications
must validate destinations and enforce their own network access policy before
making follow-up requests.
