# Architecture

Current implementation. [ADR](adr-python-first-network-framework.md) explains decisions and planned scope; [Developer Guide](developer-guide.md) shows usage.

```text
Python clients ───────┐
                      ├── NetworkRuntime ── single background consumer
REST / SSE (optional) ┘                           │
                                            DiscoveryEngine
                                                  │
                                      SSDP / mDNS / SLP / BLE
                                                  │
                                            shared queue
                                                  │
                                         ObservationRegistry
                                                  │
                                         ObservationStorage
```

- **DiscoveryEngine:** starts plugins, concurrently consumes their async streams when `discover()` is iterated, normalizes ADDED/UPDATED/REMOVED events, and updates the bounded live registry.
- **ObservationStorage:** injected async store for remembered observations; `InMemoryStorage` is not durable. Remembered does not mean currently online.
- **NetworkRuntime:** owns one engine consumer task, provides snapshots and a protocol/identifier map, and broadcasts future events to bounded subscriptions. Slow subscribers are disconnected. The engine's internal event queue remains unbounded.
- **HTTP adapter:** optional FastAPI router over the **same runtime**, without its own engine or server.

## HTTP API

When mounted at `/network`:

| Route | Purpose |
| --- | --- |
| `GET /network/discoveries` | Live observations; optional `?protocol=mdns` |
| `GET /network/discoveries/map` | Observations indexed by protocol and identifier |
| `GET /network/entities` | Read-only entity projection, optional protocol filter |
| `GET /network/discoveries/events` | Future-only SSE stream |
| `GET /network/health` | UTC timestamp, consumer status, observation count, protocols |

`discovery_running` reports whether the consumer task is alive, **not** individual plugin health. Runtime startup/shutdown is controlled by the host application's async lifespan.

## Identity and limitations

Neither map nor entity projection is a verified physical-device inventory. SSDP observations with matching valid USN UUIDs are grouped; all others remain separate. Entity IDs use protocol-qualified identity (for example, `ble:AA:BB`); entity responses include observation references rather than duplicating full observation payloads. Full evidence remains available through `/discoveries`. One TV may have several SSDP and mDNS records. Do not merge by IP, name, or BLE address alone; BLE privacy addresses may rotate. SSDP observation ports may be UDP response-source ports rather than advertised service ports. `metadata.location` contains the advertised description URL, not a verified control endpoint.

Implemented: discovery, normalization, live/historical observation contracts, background runtime, subscriptions, REST/SSE.

Deferred: protocol inspection, cross-protocol correlation, Bluetooth Classic, generic interactions/pairing, durable entity reconciliation. Vendor-specific automation remains application-owned.

The host owns logging, server security, and lifecycle. Bind the example API to localhost unless access controls are configured.
