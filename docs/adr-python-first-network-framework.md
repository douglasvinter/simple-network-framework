# ADR: Python-first network framework and optional HTTP adapter

**Status:** Accepted — incremental implementation in progress  
**Scope:** SNF architecture and consolidation of reusable networking capabilities  
**Date:** 2026-11-16

## Context

SNF currently provides protocol adapters, `DiscoveryEngine`, `DiscoveryObservation`, `ObservationRegistry`, and `ObservationStorage`. Its engine runs plugin pumps while a caller iterates `engine.discover()`. The original design intentionally excludes cross-protocol identity correlation and HTTP interfaces.

A separate application implementation demonstrated the need for a background discovery runtime, subscriber fan-out, a networking service facade, and FastAPI REST/SSE endpoints. These are reusable networking capabilities; keeping them outside SNF would make consumers reproduce framework infrastructure.

## Decision

**SNF is an embeddable, Python-first network framework.** Its core functionality is available through Python APIs without a server. An **optional** FastAPI adapter exposes the same running framework instance over HTTP; it neither owns networking behavior nor creates an independent discovery state.

SNF owns protocol discovery, **protocol-aware inspection and capability resolution**, normalized observations, network-entity resolution, enriched service inventory, runtime lifecycle, event fan-out, storage contracts, **generic service consumption and connection/session management**, and **protocol-level pairing/unpairing where supported**. SNF provides protocol capabilities, not vendor-specific device behavior. Vendor-specific integrations, device commands, application workflows, and home-automation rules belong to consuming applications.

### Boundaries

| Area | SNF | Consuming application |
| --- | --- | --- |
| Protocol discovery and normalization (SSDP, mDNS, OpenSLP, BLE, Bluetooth Classic) | Owns | Configures |
| Live observation registry and lifecycle | Owns | Reads/subscribes |
| Network identity resolution and evidence | Owns | May add application knowledge |
| Service/endpoint aggregation | Owns | Uses |
| Protocol-aware inspection and capability resolution | Fetches/parses supported service descriptions and inspects supported characteristics | Uses enriched capabilities and configures inspection policy |
| Generic service consumption and protocol operations | Owns protocol-level adapters/contracts | Chooses services and interprets results |
| Pairing/unpairing, connection and session lifecycle | Owns when supported by protocol/backend | Requests operations and applies user policy |
| Vendor-specific device integrations and commands | Does not own | Owns |
| Storage contracts and optional drivers | Owns | Selects/configures |
| REST/SSE/OpenAPI | Optional SNF adapter | Embeds router if desired |
| Automation rules, scenes, schedules | Does not own | Owns |

## Public contracts (proposed, not yet implemented)

The existing `DiscoveryEngine`, `DiscoveryObservation`, and `ObservationStorage` contracts remain the starting point. Introduce a higher-level embeddable runtime that owns a **single consumer** of the engine's discovery stream. Its exact class and method names are to be settled during implementation; illustrative usage:

```python
async with NetworkFramework(plugins=plugins, storage=storage) as network:
    observations = network.observations()
    async for event in network.events():
        ...
```

Multiple consumers must not each call `DiscoveryEngine.discover()` and independently mutate its registry. The runtime consumes one stream, publishes events to independent bounded subscribers, and provides synchronous point-in-time live snapshots. Subscriber disconnect/cancellation must not stop discovery for others.

An optional HTTP integration accepts an **existing** runtime instance:

```python
app.include_router(create_router(network), prefix="/network")
```

A convenience application factory may also be provided. The host owns runtime startup/shutdown unless it explicitly delegates that ownership. Importing SNF or its API module must never bind a port or start Uvicorn.

### Event subscription semantics

- Document whether subscriptions are future-only or include an initial snapshot; initial migration preserves future-only SSE semantics.
- Define behavior for bounded buffers and slow consumers (initial migration: disconnect slow subscriber rather than block discovery).
- Ensure subscriber registration/unregistration and shutdown are cancellation-safe.
- Document ordering and event types; avoid claiming delivery durability or replay.
- Do not conflate `REMOVED` observation events with proof that physical hardware is offline.

### Discovery, inspection, and interaction: distinct responsibilities

**Discovery observations are inputs to SNF's inventory, not its final product.** The framework must enrich protocol advertisements into an inventory of network entities, advertised services, supported protocol capabilities, endpoints, identity evidence, and inspection state. Three operations have distinct contracts and lifecycle:

1. **Discovery:** observe announcements, advertisements, and service locators without assuming they are verified, reachable, or controllable.
2. **Inspection / resolution:** fetch or query supported protocol descriptions, enumerate services/capabilities, and enrich inventory with provenance and inspection status. Inspection is a first-class SNF capability, not vendor application logic.
3. **Interaction:** explicitly consume supported services, invoke standardized actions, read/write characteristics, connect/disconnect, and pair/unpair where supported. Inspection does not itself authorize state-changing operations.

**SSDP / UPnP enrichment:** When an SSDP observation supplies a `LOCATION` URL, a configured inspector may retrieve the UPnP device description XML; parse UDN, device type, manufacturer, model, embedded devices, service types, service IDs, and description/control/event URLs; resolve SCPD descriptions to learn actions, arguments, and state variables; and place these structured capabilities in the SNF inventory. Service control remains an explicit operation. Preserve the raw advertisement and the source URL as evidence, not as a trusted identity or unrestricted request destination. Apply URL/redirect validation, local-network targeting policy, request timeouts, bounded response sizes, safe XML parsing, and appropriate caching/retries.

**BLE / GATT enrichment:** BLE advertisements identify candidate peripherals, not their full capabilities. When explicitly requested or permitted by an inspection policy, a supported BLE backend may connect, enumerate GATT services, characteristics, descriptors and properties, and read appropriate standard characteristics (for example, Device Information Service). Record UUIDs, characteristic properties, observed values where safe, inspection status, and provenance in SNF inventory. Reads may require authentication and can have device-specific side effects; do not automatically pair, write, subscribe to notifications, or assume every peripheral can be inspected. Connections must have bounded concurrency, timeouts, and reliable cleanup. BLE identity may be unstable because of privacy address rotation.

**Bluetooth Classic / BR/EDR (including audio devices):** SNF must also support Bluetooth Classic independently of BLE. Discovery should enumerate discoverable BR/EDR devices through a supported OS/backend, and inspection should use SDP or platform-provided service/profile information to identify advertised capabilities (for example, A2DP, AVRCP, HFP/HSP when exposed). SNF's inventory must distinguish Classic, BLE, and dual-mode observations and retain provenance without assuming a shared MAC address always proves stable physical identity. Generic pairing/unpairing, trust/bond state, connection/disconnection, and profile/service availability belong in SNF when supported by the host OS/backend. Platform support varies across Windows, Linux, and macOS; expose supported operations and explicit unsupported errors rather than promise uniform behavior. For audio, SNF should inspect and manage available profiles/devices using the OS Bluetooth/audio stack; **implementing an A2DP audio codec/streaming engine or vendor-specific media behavior is not an SNF requirement**. Do not assume that BLE's Bleak backend supports Classic discovery or audio profiles.

**Other discovery protocols:** mDNS/DNS-SD and OpenSLP can provide service types, endpoints, and metadata; protocol-specific inspectors may enrich services when a supported description or interrogation mechanism exists. Do not pretend the discovery protocol itself defines universal service actions or pairing.

**Inventory projection (conceptual, not an implemented schema):**

```text
NetworkEntity
  identity / correlation evidence
  protocol observations (raw evidence and lifecycle)
  manufacturer / model (when learned)
  endpoints
  services
    service type / source / description
    supported standardized actions or GATT characteristics
    required access and operation support
  inspection status / errors / last inspection
  availability evidence (not proof of physical online state)
```

Maintain distinct states for discovery, inspection, and interaction. Inspection failures must not erase valid discovery observations or be confused with device removal. Cache invalidation, reinspection, stale capabilities, and restart reconciliation need explicit semantics. SNF must expose the enriched inventory to Python clients and, optionally, read-only HTTP endpoints; the current `DiscoveryObservation` model remains available unchanged until a deliberate migration.

**Framework/application boundary:** SNF understands UPnP actions, BLE GATT characteristics, Bluetooth Classic SDP/profiles, generic protocol operations, and capability metadata. Consuming applications interpret vendor/model-specific semantics, including proprietary payloads, app launching, and appliance workflows. A writable characteristic or advertised action is not proof of a universally meaningful device command.

### Identity and entity resolution (subsequent phase)

Keep raw `DiscoveryObservation` records as protocol evidence. Add a separate network-entity projection with provenance for each correlation decision.

- Consolidate advertisements within a protocol only when that protocol supplies defensible identity evidence (e.g., SSDP UDN); preserve distinct services and their lifecycles.
- Cross-protocol correlation must use explicit matching evidence and support uncertainty; **never automatically merge solely on name, IP address, or BLE address**.
- Network entities are not necessarily physical devices. Entity IDs and relationships must remain stable or have documented reconciliation semantics.
- No cryptographic claim should be implied by a field named `verified` unless actual verification exists.
- Identity resolution must be testable without FastAPI and without a database.

### Network interactions and capability contracts (subsequent phases)

Discovery is not the framework's final boundary. SNF will expose **generic network interaction APIs** through Python and, where appropriate, its optional HTTP adapter:

- **Service consumption:** resolve an advertised service, open a protocol-supported interaction, send requests or invoke standardized operations, and return protocol-level responses/errors. A discovered service is not automatically callable; adapters must advertise supported operations.
- **Connections and sessions:** explicit connect/disconnect and session lifecycle management where the underlying protocol or library supports it, including timeouts, cancellation, cleanup, and failure reporting.
- **Pairing and unpairing:** explicit operations for protocols/backends that provide them (for example, BLE or Bluetooth Classic pairing via a suitable OS backend). Pairing is not a universal concept for SSDP, mDNS, or OpenSLP, and must not be fabricated as one.
- **Capability discovery:** describe which operations an adapter actually supports, including platform-dependent or unavailable operations. Unsupported operations must fail explicitly rather than silently succeeding.
- **Python-first and HTTP parity:** supported generic operations are callable from Python without FastAPI; HTTP routes may expose selected operations using the same services, not separate implementations.

**Interaction operations must be explicit and opt-in.** Discovery or a read-only inventory request must never implicitly pair, unpair, authenticate, open sessions, or invoke a device command. Connection and pairing APIs require clear authorization and security boundaries; exposing them over HTTP requires authentication/authorization, input validation, and conservative network binding. Do not expose an unrestricted arbitrary-target request proxy or command executor.

**Vendor boundary:** SNF can invoke a standardized UPnP action, communicate with a supported generic protocol service, or pair a Bluetooth device. A consuming application interprets the device's vendor/model-specific semantics (for example, launching an app on a particular TV, selecting an air-conditioner mode, or handling proprietary authentication). Generic protocol support does not imply SNF implements every vendor command.

These are **planned contracts**, not implemented functionality. Design each interaction API against real adapter/backend capabilities rather than assuming every discovered service is controllable.

### Storage

Retain `ObservationStorage` as the existing historical-observation contract and `InMemoryStorage` as a reference implementation. Live snapshots remain distinct from remembered observations. A persisted record is not evidence of current availability.

Later phases may introduce entity storage, reconciliation, and an optional SQLite driver after deciding persistence keys, schema evolution, restart behavior, and stale-state semantics. No database dependency is required by SNF core.

### Optional dependencies

Keep the base package usable without FastAPI, SSE, or SQL libraries. Provide an `api` extra for HTTP dependencies and optional storage extras when concrete drivers exist. Preserve the existing optional protocol extras. No new server process is required for direct Python usage.

### HTTP surface (initial migration)

Preserve the initial read-only HTTP behavior where practical:

- `GET /network/discoveries` — live observations, optional protocol filter.
- `GET /network/discoveries/map` — grouped live observations.
- `GET /network/discoveries/events` — future-only SSE with bounded per-client buffering.
- Health diagnostics may be exposed through a separate route, with runtime-health semantics explicitly documented.

Future authenticated HTTP routes may also expose supported service operations, connection/session management, and pairing/unpairing; these are **not** part of the initial read-only migration.

HTTP handlers perform validation and serialization, then delegate to SNF runtime/services. They do not instantiate their own engine. Default examples bind localhost; exposing network inventory remotely requires deliberate authentication and deployment controls.

## Implementation sequence

1. **Architecture review (this ADR):** agree on boundaries, ownership, event and lifecycle contracts.
2. **Consolidation PR:** implement the reusable background runtime, subscriber fan-out, service projection, and HTTP schemas/routes in SNF. Preserve behavior; do not implement correlation or SQL in this PR.
3. **Inspection and entity-resolution PRs:** introduce protocol-aware inspection and inventory enrichment (UPnP device/SCPD descriptions; opt-in BLE GATT enumeration; Bluetooth Classic SDP/profile inspection), then evidence-based entity correlation with provenance and lifecycle tests. Inspection may provide the stronger identifiers needed for correlation; separate into focused PRs.
4. **Persistence PR:** explicit durable-inventory and reconciliation contracts; add SQLite only after contract tests.
5. **Generic interaction contracts and adapters:** add service consumption, supported connection/session operations, and BLE/Classic pairing/unpairing as focused, independently tested increments; validate real backend/platform support and access controls. Bluetooth Classic discovery and audio-profile awareness require a backend separate from BLE-only scanning.
6. **Real-device validation:** SSDP LOCATION/SCPD enrichment, BLE GATT inspection, Bluetooth Classic discovery/SDP/audio-profile detection, mDNS, OpenSLP, service invocation, supported pairing flows, disconnect/reconnect, multiple clients, restart and cancellation behavior.
7. **Integration and release readiness:** validate Python and HTTP contracts with independent consumers and real devices before considering a stable package release.

## Acceptance criteria for consolidation

- Direct Python usage works without installing HTTP dependencies.
- Optional FastAPI router uses the same runtime and live inventory as Python callers.
- Only one discovery-consumer task exists per runtime; multiple SSE subscribers do not duplicate discovery.
- Existing SNF protocol tests and new REST/SSE contract tests pass.
- Event fan-out handles slow clients, disconnects, cancellation, and shutdown.
- API import has no startup/network side effects.
- `py.typed` and strict typing checks are considered for published Python consumers.
- Documentation and examples cover embedding in an existing application.
- No home-automation-specific classes or dependency on a consuming application are introduced.
- Generic interaction and pairing contracts are explicitly deferred from the consolidation PR, but remain part of SNF's planned scope.

## Alternatives considered

1. **Keep API/runtime in a consuming application:** rejected because generic consumers would reimplement networking infrastructure.
2. **Make SNF a mandatory standalone server:** rejected because it compromises embedding and introduces an unnecessary process boundary.
3. **Make FastAPI mandatory:** rejected because core Python consumers do not need an HTTP stack.
4. **Move correlation into consuming applications:** rejected as the default because reusable network-entity resolution belongs in SNF; application-specific interpretation remains outside it.
5. **Implement migration, inspection, correlation, and persistence together:** rejected due to excessive behavior and contract changes in one PR.
6. **Treat advertisements as the final inventory:** rejected because the framework must resolve and describe actual protocol services and capabilities, while retaining raw observations as evidence.

## Consequences and risks

The framework becomes more capable and owns more lifecycle complexity, including explicit connection and pairing state in future phases. The implementation must avoid double consumption, unsafe correlation, unbounded queues, blocking slow subscribers, and accidental HTTP exposure. The current implementation is documented separately in [Architecture](architecture.md) and the [Developer Guide](developer-guide.md). This ADR remains the record of the target architecture; planned capabilities must not be mistaken for shipped features.
