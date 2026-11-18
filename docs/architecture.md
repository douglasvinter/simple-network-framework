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

- **DiscoveryEngine:** starts plugins, concurrently consumes their async streams when `discover()` is iterated, normalizes ADDED/UPDATED/REMOVED events and emits EVICTED on capacity pressure, and updates the bounded live registry.
- **ObservationStorage:** injected async store for remembered observations; `InMemoryStorage` is not durable. Remembered does not mean currently online. Neither removal nor capacity eviction deletes a remembered observation.
- **NetworkRuntime:** owns one engine consumer task, provides snapshots and a protocol/identifier map, and broadcasts future events to bounded subscriptions. Slow subscribers are disconnected. The engine's internal event queue remains unbounded. A subscription is future-only; request a snapshot separately for initial state.
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

## Live inventory, eviction, and remembered observations\n\nThe registry is a bounded live *observation cache*, not an authoritative online-device list. A plugin emits REMOVED when its protocol reports departure; registry capacity pressure instead emits **EVICTED** before the replacement ADDED event. EVICTED only means the framework discarded an entry to respect its memory bound; it does **not** assert that a device went offline. Plugin authors must not emit EVICTED. Duplicate unchanged observations do not emit updates.\n\nThe storage backend records observations that were seen previously. It retains them after REMOVED and EVICTED until explicitly deleted. Consumers should use the live snapshot for the current discovery view, remembered storage for history, and treat future-only events as incremental changes. Eviction may cause a still-present device to be ADDED again if rediscovered.\n\n## Identity and limitations

Neither map nor entity projection is a verified physical-device inventory. SSDP observations with matching valid USN UUIDs are grouped; all others remain separate. Entity IDs use protocol-qualified identity (for example, `ble:AA:BB`); entity responses include observation references rather than duplicating full observation payloads. Full evidence remains available through `/discoveries`. One TV may have several SSDP and mDNS records. Do not merge by IP, name, or BLE address alone; BLE privacy addresses may rotate. SSDP observation ports may be UDP response-source ports rather than advertised service ports. `metadata.location` contains the advertised description URL, not a verified control endpoint.

Implemented: discovery, normalization, live/historical observation contracts, background runtime, subscriptions, REST/SSE.

Deferred: speculative cross-protocol correlation, cache TTLs, generic interactions/pairing, durable entity reconciliation. Inspection is protocol-specific and optional. Vendor-specific automation remains application-owned.

The host owns logging, server security, and lifecycle. Bind the example API to localhost unless access controls are configured.
