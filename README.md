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

## Requirements

- Python 3.11 or newer.
- A network interface connected to the local network where the devices or services
  you want to discover are available.
- Multicast traffic must be supported by the network for SSDP and mDNS discovery.
- A supported Bluetooth adapter and operating-system Bluetooth stack for BLE discovery.
- Install Python protocol dependencies through the `all` extra:

```bash
python -m pip install 'simple-network-framework[all]'
```

This installs the framework and its SSDP, mDNS, and BLE backends. SLP has an additional
native dependency: the OpenSLP `slptool` executable must be installed separately
and available on `PATH`. OpenSLP is not a Python package, and availability and
installation steps vary by operating system.

## Platform setup

### Windows

**What you need**

- Windows 10 or newer.
- Python 3.11+ (the Python launcher, `py`, is recommended).
- Access to the same LAN as the devices you want to discover.
- Windows Defender Firewall configured to allow Python network access on the
  appropriate network profile.
- For SLP only: a Windows-compatible OpenSLP distribution that provides
  `slptool.exe`. SNF does not bundle this executable; SLP availability on Windows
  depends on the external distribution you install.
- For BLE discovery: a supported Bluetooth adapter and Windows Bluetooth stack.

**Install**

Run these commands in PowerShell from the project directory:

```powershell
py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

If your PowerShell execution policy prevents virtual-environment activation, you
can use the environment's Python executable directly instead:

```powershell
.\\.venv\\Scripts\\python.exe -m pip install --upgrade pip
.\\.venv\\Scripts\\python.exe -m pip install -e ".[all]"
```

**Run the example**

```powershell
python .\\examples\\discover_all.py
```

**Windows networking notes**

- Allow the Python executable through Windows Defender Firewall on your **Private**
  network profile when prompted. Do not enable broad access on Public networks
  unless you understand and intend that exposure.
- SSDP uses UDP multicast (IPv4 group `239.255.255.250`, port `1900`); mDNS uses
  UDP multicast (IPv4 group `224.0.0.251`, port `5353`). Firewall rules, endpoint
  security software, or network equipment can block this traffic.
- VPNs, multiple active network adapters, guest Wi-Fi, client isolation, and
  VLAN/subnet boundaries can prevent multicast discovery.
- Discovery is generally intended for devices reachable on the same local network.
  Routers do not normally forward link-local multicast between subnets.

### Linux

**What you need**

- A supported Linux distribution.
- Python 3.11+ and the `venv` / `pip` components for that Python installation.
- Access to the same LAN as the devices you want to discover.
- A firewall and network configuration that permit the required multicast traffic.
- For SLP only: OpenSLP client utilities providing the `slptool` executable.
- For BLE discovery: a supported Bluetooth adapter and BlueZ (the Linux Bluetooth
  protocol stack), with the required user/session permissions.

On Debian or Ubuntu, if virtual-environment support is not already installed,
you may need the distribution's `python3-venv` package. Install OpenSLP using
your distribution's package manager; package names vary by distribution.

**Install**

Run these commands from the project directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[all]'
```

**Run the example**

```bash
python examples/discover_all.py
```

**Linux networking notes**

- Check your distribution's firewall configuration (for example, UFW, firewalld,
  or nftables) if discovery returns no services. Permit the relevant SSDP and mDNS
  UDP multicast traffic on the intended local interface/network.
- SSDP uses UDP multicast (IPv4 group `239.255.255.250`, port `1900`); mDNS uses
  UDP multicast (IPv4 group `224.0.0.251`, port `5353`).
- VPNs, multiple interfaces, container bridges, guest Wi-Fi, client isolation, and
  VLAN/subnet boundaries can affect which multicast announcements are visible.
- Running the framework as root is not normally required for these discovery
  protocols. Prefer configuring the firewall and interface permissions rather
  than running the application with elevated privileges.

### macOS

**What you need**

- macOS 12 or newer.
- Python 3.11+ (for example, from python.org or Homebrew).
- Access to the same LAN as the devices you want to discover.
- Local Network access for the terminal application running Python, if macOS
  requests permission.
- For SLP only: an OpenSLP installation that provides the `slptool` executable
  and makes it available on `PATH`. SNF does not bundle OpenSLP.
- For BLE discovery: a supported Bluetooth adapter and macOS Bluetooth permissions.

**Install**

Run these commands in Terminal from the project directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[all]'
```

**Run the example**

```bash
python examples/discover_all.py
```

**macOS networking notes**

- When macOS asks whether the terminal application (such as Terminal or iTerm)
  may access devices on your local network, allow it if you want to discover
  local services. You can review this permission under **System Settings >
  Privacy & Security > Local Network**.
- The macOS application firewall and third-party endpoint security tools may
  affect incoming discovery traffic. Review their rules if devices are not found.
- SSDP uses UDP multicast (IPv4 group `239.255.255.250`, port `1900`); mDNS uses
  UDP multicast (IPv4 group `224.0.0.251`, port `5353`). macOS includes Bonjour
  support for mDNS, but SNF still installs and uses its Python `zeroconf` backend.
- VPNs, multiple network interfaces, guest Wi-Fi, client isolation, and
  VLAN/subnet boundaries can prevent multicast discovery.

## Quick start

```python
import asyncio
import logging

from snf import DiscoveryEngine, create_plugins

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    selected = create_plugins()

    async with DiscoveryEngine(selected) as discovery:
        async for event in discovery.discover():
            device = event.device
            logger.info(
                "%s %s %s %s",
                event.state,
                device.protocol,
                device.name,
                device.endpoints,
            )


asyncio.run(main())
```

SNF logs and skips plugins that fail construction or startup by default. Use\n`create_plugins(strict=True)` to fail on construction, and\n`DiscoveryEngine(selected, strict=True)` to fail on startup.\n\nThe engine starts plugins concurrently and merges their event streams. A consumer
can inspect the current immutable inventory through `engine.devices`, or retrieve
a protocol-scoped record with `engine.get_device(protocol, identifier)`.

To include SLP, install OpenSLP and make sure `slptool` is on `PATH` before
instantiating its adapter. The example script selects SLP automatically when
`slptool` is available.

## Domain model

- `Device`: a protocol-scoped discovered inventory record.
- `Service`: a service advertised by a device.
- `Endpoint`: a transport-specific locator, such as an IP address/port or BLE address.
- `DiscoveryEvent`: an ADDED, UPDATED, or REMOVED lifecycle event for a device.

BLE records include advertisement information such as RSSI, transmit power,
advertised service UUIDs, manufacturer data, and service data. BLE discovery does
not establish a connection or pair with a peripheral.

BLE devices are considered removed after `device_timeout` seconds without a
received advertisement (15 seconds by default). RSSI-only updates are emitted
only when the signal changes by at least 5 dBm by default, avoiding a noisy event
stream. This is an observation timeout, not proof that the physical device is
powered off or out of range.

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

The SLP adapter delegates RFC 2608 wire protocol behavior to OpenSLP and uses
its command-line interface rather than an unmaintained Python binding.

## Third-party plugins

Register an entry point in your plugin distribution:

```toml
[project.entry-points."snf.protocols"]
my-protocol = "my_snf_plugin:MyProtocolPlugin"
```

A plugin implements async `start()`, async-iterator `discover()`, and async
`stop()` methods. It yields `DiscoveryEvent` objects. The plugin owns its protocol
resources; the engine handles lifecycle, concurrency, aggregation and inventory.

## Logging

SNF uses Python's standard `logging` hierarchy (`snf.engine`, `snf.plugins`,
`snf.adapters.*`) and installs only a `NullHandler` on `snf`. SNF does not
configure global logging or choose output destinations. Consuming applications
control handlers, levels, formatting, and log files. See
[Logging](docs/logging.md) for examples of shared and separate log files.

## Development

```bash
python -m pip install -e '.[all,dev]'
python -m pytest
ruff check .
mypy src
```

## Security

Discovery data is untrusted input. SNF does not automatically fetch SSDP LOCATION
URLs, connect to discovered devices, or invoke discovered services. Applications
must validate destinations and enforce their own network access policy before
making follow-up requests.
