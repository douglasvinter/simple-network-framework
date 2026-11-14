# Simple Network Framework

An asyncio-based, extensible framework for local network service discovery.

SNF delegates wire-protocol implementation to established libraries. It provides a
common service model, lifecycle management, event de-duplication, and a Python
entry-point plugin system.

## Requirements

- Python 3.11 or newer.
- A network interface connected to the local network where the devices or services
  you want to discover are available.
- Multicast traffic must be supported by the network for SSDP and mDNS discovery.
- Install Python protocol dependencies through the `all` extra:

```bash
python -m pip install 'simple-network-framework[all]'
```

This installs the framework and its SSDP and mDNS backends. SLP has an additional
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

**Install**

Run these commands in PowerShell from the project directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

If your PowerShell execution policy prevents virtual-environment activation, you
can use the environment's Python executable directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
```

**Run the example**

```powershell
python .\examples\discover_all.py
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

## Quick start

```python
import asyncio
from snf import DiscoveryEngine, load_plugins


async def main() -> None:
    plugins = load_plugins()
    selected = [plugins[name]() for name in ("ssdp", "mdns")]
    async with DiscoveryEngine(selected) as discovery:
        async for service in discovery.discover():
            print(service)


asyncio.run(main())
```

To browse specific DNS-SD types, instantiate the adapter directly:

```python
from snf.adapters.mdns import MDNSPlugin

mdns = MDNSPlugin(["_http._tcp.local.", "_ssh._tcp.local."])
```

To include SLP, install OpenSLP and make sure `slptool` is on `PATH` before
instantiating its adapter:

```python
from snf.adapters.slp import SLPPlugin

slp = SLPPlugin()
```

## Event de-duplication

The discovery engine maintains a bounded in-memory registry (4,096 services by
default). Repeated identical announcements are suppressed. A change to a known
service's address, port, or metadata is emitted as UPDATED; a known service's
REMOVED event is emitted once and clears its registry entry, allowing a later
announcement to be emitted as ADDED again.

Registry identity is protocol + service name + service type. It intentionally
does not merge SSDP and mDNS records into a physical-device identity: cross-protocol
device correlation needs a separate model and stronger identifiers. Tune the bound
with `DiscoveryEngine(..., dedupe_cache_size=...)`.

## Third-party plugins

Register an entry point in your plugin distribution:

```toml
[project.entry-points."snf.protocols"]
my-protocol = "my_snf_plugin:MyProtocolPlugin"
```

A plugin implements async start(), discover(), and stop() methods. It owns its
sockets and protocol state; the engine handles lifecycle and merges event streams.

## Included adapters

| Adapter | Backend | Capabilities |
| --- | --- | --- |
| SSDP / UPnP | async-upnp-client | Search responses and device metadata |
| mDNS / DNS-SD | python-zeroconf | Service browsing, resolution, IPv4/IPv6 |
| SLPv2 | OpenSLP slptool | User Agent lookups, scopes and Directory Agent discovery |

The SLP adapter delegates RFC 2608 wire protocol behavior to OpenSLP and uses
its command-line interface rather than an unmaintained Python binding.

## Development

Install the project and development tools from a checkout:

```bash
python -m pip install -e '.[all,dev]'
pytest
ruff check .
mypy src
```

## Security

Discovery responses are untrusted input. SNF does not automatically fetch SSDP
LOCATION URLs or invoke discovered services. Applications must validate destinations
and enforce their own network access policy before making follow-up requests.
