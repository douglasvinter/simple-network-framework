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
| Protocol discovery and normalization (SSDP, mDNS, BLE, Bluetooth Classic) | Owns | Configures |
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

### Discovery, inspection, and interaction

1. **Discovery:** collect advertisements and locators without treating them as verified or actionable.
2. **Inspection:** optionally retrieve and parse supported service descriptions, with provenance, timeouts, bounded responses, safe parsing, and target/redirect validation.
3. **Interaction:** explicitly invoke supported protocol operations; inspection must not implicitly pair, write, or control devices.

Planned inspectors include UPnP device/SCPD descriptions, opt-in BLE GATT enumeration, Bluetooth Classic SDP/profiles, and supported service metadata for mDNS. Bluetooth Classic needs a separate backend from Bleak BLE scanning. Audio-profile awareness is in scope; implementing an audio codec/streaming engine is not. Platform capabilities vary: unsupported operations must fail explicitly.

Keep discovery, inspection, and interaction states separate. Inspection failures must not erase valid observations. A future enriched entity projection may include identity evidence, services, endpoints, capabilities, and inspection status; its schema is not implemented.

### Identity and entity resolution (subsequent phase)

Keep raw `DiscoveryObservation` records as protocol evidence. Add a separate network-entity projection with provenance for each correlation decision.

- Consolidate advertisements within a protocol only when that protocol supplies defensible identity evidence (e.g., SSDP UDN); preserve distinct services and their lifecycles.
- Cross-protocol correlation must use explicit matching evidence and support uncertainty; **never automatically merge solely on name, IP address, or BLE address**.
- Network entities are not necessarily physical devices. Entity IDs and relationships must remain stable or have documented reconciliation semantics.
- No cryptographic claim should be implied by a field named `verified` unless actual verification exists.
- Identity resolution must be testable without FastAPI and without a database.

### Generic interaction (subsequent phases)

SNF will expose supported protocol-level service operations, connections/sessions, and pairing/unpairing where the backend permits. These must be explicit, opt-in, cancellable, and bounded by timeouts and authorization. Pairing is not a universal operation across discovery protocols. Python remains the primary API; HTTP may expose selected operations through the same services, with authentication and input validation. Never provide an unrestricted arbitrary-target proxy. Vendor/model-specific commands and automation stay in consuming applications.

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

1. Review architecture and contracts (this ADR).
2. Implement single-consumer runtime, event subscriptions, and optional read-only HTTP adapter (PR #8).
3. Add inspection and evidence-based entity resolution in focused PRs.
4. Define durable entity/reconciliation contracts before choosing SQLite.
5. Add supported generic interactions, pairing and Bluetooth Classic separately.
6. Validate against real devices, restarts, failures and multiple clients before release.

## Acceptance criteria for consolidation

- Python usage works without HTTP dependencies; optional HTTP shares the same runtime and inventory.
- Exactly one engine consumer per runtime; bounded subscribers cannot block discovery.
- Cancellation, shutdown, slow clients and API import side effects are tested.
- Existing protocol and new HTTP tests pass; documentation and examples cover embedding.
- No vendor-specific automation or premature correlation/persistence in PR #8.

## Alternatives considered

1. **Keep API/runtime in a consuming application:** rejected because generic consumers would reimplement networking infrastructure.
2. **Make SNF a mandatory standalone server:** rejected because it compromises embedding and introduces an unnecessary process boundary.
3. **Make FastAPI mandatory:** rejected because core Python consumers do not need an HTTP stack.
4. **Move correlation into consuming applications:** rejected as the default because reusable network-entity resolution belongs in SNF; application-specific interpretation remains outside it.
5. **Implement migration, inspection, correlation, and persistence together:** rejected due to excessive behavior and contract changes in one PR.
6. **Treat advertisements as the final inventory:** rejected because the framework must resolve and describe actual protocol services and capabilities, while retaining raw observations as evidence.

## Consequences and risks

The framework becomes more capable and owns more lifecycle complexity, including explicit connection and pairing state in future phases. The implementation must avoid double consumption, unsafe correlation, unbounded queues, blocking slow subscribers, and accidental HTTP exposure. The current implementation is documented separately in [Architecture](architecture.md) and the [Developer Guide](developer-guide.md). This ADR remains the record of the target architecture; planned capabilities must not be mistaken for shipped features.
