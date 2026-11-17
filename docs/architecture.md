# Architecture — current implementation

This document describes **implemented** SNF components and contracts as of PR #8.
For architectural decisions, trade-offs, and future capabilities, see the
[Python-first framework ADR](adr-python-first-network-framework.md).
For usage, see the [Developer Guide](developer-guide.md); for task and coroutine
details, see [Async Discovery Lifecycle](async-discovery-lifecycle.md).

## Components and ownership

```text
                 Python client                 FastAPI REST / SSE (optional)
                       |                                |
                       +---------------+----------------+
                                       |
                                 NetworkRuntime
                            snapshots / map / subscribe
                                       |
                           one background consumer task
                                       |
                                 DiscoveryEngine
                                       |
                    +----------+-------+---------+
                    |          |       |         |
                   SSDP       mDNS     BLE      OpenSLP
                    |          |       |         |
                    +----------+-------+---------+
                                       |
                            shared asyncio event queue
                                       |
                             ObservationRegistry
                         deduplication / live snapshots
                                       |
                               ObservationStorage
                              historical observations
```

`DiscoveryEngine` starts the selected plugins and consumes their async streams
concurrently when `discover()` is iterated. The registry normalizes ADDED,
UPDATED and REMOVED observations and maintains a bounded live snapshot.
`ObservationStorage` is an injected asynchronous historical-record contract;
`InMemoryStorage` is the bundled non-durable implementation. Live and remembered
observations have different availability semantics.

`NetworkRuntime` is an optional higher-level owner: it enters the engine's
context and consumes `discover()` exactly once in a background task. Independent
subscribers receive future-only events through bounded queues; slow subscribers
are disconnected rather than blocking the consumer. The engine's internal
merge queue is currently unbounded. The runtime and HTTP adapter share the same
inventory. The HTTP adapter does not create an engine or start a server.

## Implemented HTTP interface

Mount `create_router(runtime)` under `/network`:

| Endpoint | Semantics |
| --- | --- |
| `GET /network/discoveries` | Live normalized observations; optional protocol filter |
| `GET /network/discoveries/map` | Raw observations indexed by protocol and identifier |
| `GET /network/discoveries/events` | Future-only SSE events, bounded per client |
| `GET /network/health` | Status, UTC timestamp, background consumer state, observation count and protocols |

`discovery_running` reports whether the runtime's background consumer task is
alive. It is **not** an HTTP start/stop control and does not establish that every
plugin is healthy. The runtime starts and stops through its async context.

## Identity and observation boundaries

`DiscoveryObservation.identity` is `(protocol, identifier)`. The map is **not**
a deduplicated device inventory. One physical TV may advertise multiple SSDP
USNs and mDNS services; records remain distinct. Shared IPs, names, or BLE
addresses alone are not sufficient evidence to merge observations. BLE addresses
may rotate for privacy. A future entity projection must preserve correlation
evidence and uncertainty; it is not implemented in PR #8.

SSDP response-source UDP ports may currently appear in observation endpoints.
These ports are not necessarily the advertised service or device-description
ports. The SSDP `LOCATION` URL is retained in metadata as a locator, not
automatically fetched or treated as a validated control endpoint. Protocol-aware
inspection, UPnP XML/SCPD parsing and service endpoint resolution are deferred.

## Implemented versus planned

Implemented: SSDP, mDNS, BLE and OpenSLP discovery; observation normalization,
live registry, injected historical storage, single-consumer runtime, bounded
event subscriptions, optional REST/SSE/health router.

Planned in separate increments: protocol-aware inspection, evidence-based
entity correlation, Bluetooth Classic, supported generic protocol operations,
pairing and connection management, durable entity reconciliation and storage.
Vendor-specific control and home-automation orchestration are outside SNF.

## Lifecycle and operational constraints

The host application owns the runtime lifespan and any HTTP server. Installing
`[api]` or `[all]` makes the HTTP dependencies available but does not start
Uvicorn automatically. Default examples bind localhost; inventory endpoints
should not be exposed to untrusted clients without application-level security.
Plugin startup and pump failures are logged; runtime health does not provide
per-plugin readiness. Discovery events represent protocol evidence rather than
proof that a physical device is online.
