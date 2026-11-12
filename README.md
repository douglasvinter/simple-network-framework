# Simple Network Framework

An asyncio-based, extensible framework for local network service discovery.

SNF delegates wire-protocol implementation to established libraries. It provides a
common service model, lifecycle management, event de-duplication, and a Python
entry-point plugin system.

## Requirements

- Python 3.11 or newer.
- Install Python protocol dependencies through extras:

```bash
python -m pip install 'simple-network-framework[all]'
```

For SLP, install OpenSLP separately so the OpenSLP slptool executable is available
on PATH. OpenSLP is an OS-level dependency, not a Python wheel. Package names vary
by platform.

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

To include SLP, instantiate its adapter after installing OpenSLP:

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
