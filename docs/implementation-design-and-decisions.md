# Implementation Design and Decisions

## 1. Purpose

Simple Network Framework (SNF) is an asynchronous Python framework for discovering devices and advertised services on local networks. It normalizes observations from different discovery protocols into a common domain model and maintains a bounded live device inventory and writes observations to an injected storage driver.

SNF is deliberately a discovery and inventory library. It is not a device-control or home-automation platform.

### In scope

- Discover devices and services through independent protocol adapters.
- Normalize protocol-specific observations into common models.
- Run multiple discovery adapters concurrently.
- Publish device lifecycle events.
- Maintain a bounded in-memory inventory.
- Suppress duplicate observations and expose inventory snapshots/lookups.
- Allow third parties to extend discovery through Python package entry points.

### Out of scope

- Pairing or unpairing Bluetooth devices.
- Establishing general-purpose device sessions or managing connections.
- Invoking device APIs, launching TV applications, or controlling appliances.
- Automation rules, schedules, scenes, and workflows.
- Bundled database drivers, schema management, and retention policies.
- Automatic correlation of observations from different protocols into one physical device.

These responsibilities can be implemented by a separate consumer such as `simple-home-automation`.

## 2. High-level architecture

The framework is composed of five cooperating areas:

1. **Protocol adapters** observe their own protocols and emit normalized `DiscoveryEvent` objects.
2. **DiscoveryEngine** starts adapters, runs their asynchronous event streams concurrently, and merges the streams.
3. **DeviceRegistry** applies lifecycle semantics, suppresses duplicate observations, and maintains the current inventory.
4. **InventoryStorage** defines asynchronous key/value operations for remembered device records, with `InMemoryStorage` as the bundled reference implementation.
5. **Consumer application** receives events and queries live or remembered records.

```text
                    Consumer application
                            |
                   async for event in
                   engine.discover()
                            |
                     DiscoveryEngine
                  /          |          \
             SSDP pump    mDNS pump    BLE pump ... SLP pump
                 |           |           |
             SSDPPlugin  MDNSPlugin   BLEPlugin
                 |           |           |
             protocol-specific libraries / OS APIs
                  \          |          /
                    asyncio event queue
                            |
                      DeviceRegistry
                            |
                 bounded live in-memory inventory
                            |
                    ADDED / UPDATED
                            v
                    InventoryStorage
                            |
                  injected storage driver
```

The engine does not need to understand SSDP, DNS-SD, SLP, or BLE. Each adapter owns protocol-specific behavior and translates its observations into the shared model.

## 3. Domain model

The public models are defined in `src/snf/models.py`.

### Device

A `Device` is the inventory record produced by a protocol adapter. It contains:

- `protocol`: protocol namespace, such as `ssdp`, `mdns`, `slp`, or `ble`.
- `identifier`: identifier supplied or derived by that protocol.
- `name`: human-readable name where available.
- `endpoints`: transport-specific ways to locate the device.
- `services`: services advertised by the device.
- `metadata`: additional protocol-specific observations.

A device's identity is the tuple `(protocol, identifier)`, exposed by `Device.identity`.

### Service

A `Service` describes an advertised service. It can include a service type, endpoints, and metadata.

### Endpoint

An `Endpoint` describes a transport-specific locator. Examples include an IP address and optional port, or a BLE address. An endpoint is discovery information; it is not an established connection.

### DiscoveryEvent and DiscoveryState

A `DiscoveryEvent` associates a device observation with one of three lifecycle states:

- `ADDED`: a device has entered the current inventory.
- `UPDATED`: a known device's meaningful observed data changed.
- `REMOVED`: a known device is no longer present according to the adapter's discovery semantics.

The registry may normalize an adapter's incoming state before the consumer sees it. For example, a repeated `ADDED` observation for an existing device becomes `UPDATED` only if the device data changed.

## 4. Identity and cross-protocol correlation

**Decision:** device identity is protocol-scoped.

The same physical TV may be discovered through SSDP and mDNS and appear as two inventory records. This is intentional.

Names, IP addresses, service names, and BLE addresses are not universally stable identifiers. BLE addresses may rotate for privacy, IP addresses may change, and a service instance is not necessarily a physical-device identity. Automatically merging records using weak evidence could incorrectly combine different devices.

A future consumer may implement a correlation layer when it has stronger evidence or application-specific knowledge. That layer should not be hidden inside protocol discovery.

## 5. Plugin contract and extensibility

The plugin contract is defined by `DiscoveryPlugin` in `src/snf/plugins.py`.

Every plugin provides:

- `name`: unique protocol name within an engine instance.
- `async start()`: allocate resources and begin observing the protocol.
- `discover()`: return an asynchronous iterator yielding `DiscoveryEvent` values.
- `async stop()`: stop observation and release resources owned by the plugin.

Plugins are discovered through the `snf.protocols` Python entry-point group. This allows a separately distributed package to provide an adapter without changing the SNF engine.

**Decision:** adapters own their protocol resources and protocol-specific normalization. The engine owns orchestration and inventory semantics. This keeps the core independent from optional protocol dependencies.

## 6. Asynchronous execution model

**Decision:** use `asyncio` and asynchronous event streams.

The engine starts all configured plugins with `asyncio.gather()`. When `discover()` is consumed, it creates one task per plugin. Each task consumes that plugin's async iterator and places yielded events onto a shared `asyncio.Queue`.

The engine consumes the queue, processes events through the registry, and yields normalized events to the application.

This provides concurrent observation without requiring a separate thread per protocol. A plugin may internally use callbacks from a protocol library, but it must marshal observations into its async iterator safely.

The engine is an asynchronous context manager so that callers have a clear resource lifecycle:

```python
async with DiscoveryEngine(plugins, storage=InMemoryStorage()) as engine:
    async for event in engine.discover():
        ...
```

Leaving the context calls `stop()`, which stops all configured plugins.

See [Async Discovery Lifecycle](async-discovery-lifecycle.md) for the detailed execution trace.

## 7. In-memory inventory

The `DeviceRegistry` in `src/snf/registry.py` is the current inventory implementation.

- It stores the latest `Device` per protocol-scoped identity.
- It returns `ADDED` for the first observation.
- It suppresses an identical subsequent observation.
- It returns `UPDATED` when an existing record changes.
- It returns `REMOVED` only when the identity is currently present.
- It exposes a tuple snapshot and protocol-scoped lookup.
- It is bounded; the default capacity is 4,096 entries.

When capacity is exceeded, the registry evicts the oldest entry. Eviction is a capacity-management behavior and does not currently emit a `REMOVED` event.

**Decision:** the storage contract is mandatory, but database implementations are intentionally deferred. The live registry is process-local; remembered records live in the caller-supplied storage driver. The reference `InMemoryStorage` is not durable.

## 8. Adapter responsibilities and current implementations

| Adapter | Backend | Discovery behavior |
| --- | --- | --- |
| SSDP | `async-upnp-client` | Periodic SSDP searches; emits device/service observations from responses. |
| mDNS / DNS-SD | `python-zeroconf` | Browses service types and resolves service instances; callback observations are forwarded to an async queue. |
| SLP | OpenSLP `slptool` | Periodically queries service types and service URLs through the external executable. |
| BLE | Bleak | Scans advertisements and emits peripheral observations; stale observations expire after a configurable timeout. |

Protocol dependencies are optional extras. SLP additionally requires the native OpenSLP `slptool` executable on `PATH`.

### Important adapter semantics

- SSDP periodically searches and reports responses. The current adapter does not independently expire previously seen SSDP devices.
- mDNS uses service-browser callbacks and resolves service records. A service removal is not proof that the physical device has powered off.
- SLP periodically queries service URLs and currently tracks URLs seen by that adapter; it does not currently emit expiry/removal events for URLs that disappear from later query results.
- BLE observes advertisements only. It does not pair, connect, or enumerate GATT characteristics. Its removal timeout means no advertisement was observed for the configured period; it is not proof that a device is powered off.

Consumers should interpret lifecycle events as protocol observations, not authoritative physical-device state.

## 9. Error handling and lifecycle

- Plugin startup is concurrent. If startup fails, the engine attempts to stop all configured plugins and raises the first startup failure.
- A plugin pump logs an exception and ends that plugin's stream. The other plugin streams continue.
- Cancellation of a pump is propagated so the engine can shut down cleanly.
- During shutdown, the engine attempts to stop every plugin even if one plugin's `stop()` fails; shutdown failures are logged.
- Plugins should make `stop()` safe to call after partial startup, and should release every resource they own.

The engine currently does not expose a structured collection of runtime plugin failures to consumers. They are logged. This is a possible future improvement if consumers need programmatic health reporting.

## 10. Key design decisions

| Decision | Rationale |
| --- | --- |
| Keep SNF focused on discovery and inventory | Prevents protocol discovery from becoming coupled to device control or automation. |
| Use a protocol-neutral domain model | Consumers can work with one event and inventory API regardless of protocol. |
| Use protocol-scoped identity | Avoids unsafe cross-protocol guesses about physical identity. |
| Use asyncio and async iterators | Fits I/O-bound discovery and supports concurrent protocol streams. |
| Keep protocol implementations in adapters | Core orchestration does not depend on each protocol's library or wire format. |
| Load third-party adapters through entry points | Enables independent plugin distributions. |
| Require an injected storage contract | Support application-defined persistence without bundling a database or compromising fast live snapshots. |
| Delegate protocol implementations to established libraries | Reduces custom protocol code and maintenance burden. |

## 11. Current limitations and future considerations

The following are explicit limitations, not guarantees the current framework already solves:

- No bundled database implementation; historical records are available through the injected storage driver.
- No cross-protocol device correlation.
- No structured runtime health API for failed plugin streams.
- No universal expiry policy across all protocols.
- No control, pairing, or connection APIs.
- No guarantee that a discovered endpoint is reachable or safe to contact.
- The registry's capacity eviction does not currently notify consumers.
- Discovery results depend on network topology, multicast behavior, adapter support, operating-system permissions, and protocol-specific visibility.

Future changes should preserve the separation between protocol adapters, orchestration, inventory, and consuming applications.


## Injected inventory storage decision

`DiscoveryEngine` requires `storage: InventoryStorage` as a keyword-only constructor argument. The live `DeviceRegistry` remains the source for synchronous snapshots, deduplication, and event normalization. Storage is a separate async key/value contract (`get`, `upsert`, `remove`, `snapshot`) keyed by `(protocol, identifier)`. Only normalized ADDED/UPDATED events are upserted; REMOVED does not erase remembered records. `await engine.saved_devices()` retrieves historical records without presenting them as currently online. Storage exceptions propagate directly. Drivers own retry and recovery policies; the registry may suppress identical observations after a failed write. The consumer owns storage resource lifecycle. `InMemoryStorage(InventoryStorage)` is the reference implementation, with no bundled database. See [Inventory Storage](developer-guide.md#10-inventory-storage-and-application-boundaries).
