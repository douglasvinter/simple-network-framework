# Simple Network Framework

An asyncio-based, extensible framework for local network service discovery.

SNF delegates wire-protocol implementation to established libraries. It provides a
common service model, lifecycle management, a concurrent event stream, and a Python
entry-point plugin system.

## Requirements

- Python 3.11 or newer.
- Install protocol support through extras:

```bash
python -m pip install 'simple-network-framework[all]'
```

Or install only what you need:

```bash
python -m pip install 'simple-network-framework[ssdp]'
python -m pip install 'simple-network-framework[mdns]'
```

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

SLP is not registered yet: a native Python implementation with sufficient
maintenance and interoperability evidence has not been selected. We will not ship
a placeholder or partial protocol implementation.

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
