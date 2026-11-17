# ADR: Python-first network framework and optional HTTP adapter

**Status:** Proposed — review before implementation  
**Scope:** SNF architecture and migration of reusable functionality from SHA  
**Date:** 2026-11-16

## Context

SNF currently provides protocol adapters, `DiscoveryEngine`, `DiscoveryObservation`, `ObservationRegistry`, and `ObservationStorage`. Its engine runs plugin pumps while a caller iterates `engine.discover()`. The original design intentionally excludes cross-protocol identity correlation and HTTP interfaces.

The separate SHA application subsequently introduced a background `DiscoveryManager`, subscriber fan-out, a `NetworkDiscoveryService`, and FastAPI REST/SSE endpoints. These are reusable networking capabilities rather than home-automation domain behavior. Keeping them outside SNF makes consumers reproduce framework infrastructure.

## Decision

**SNF is an embeddable, Python-first network framework.** Its core functionality is available through Python APIs without a server. An **optional** FastAPI adapter exposes the same running framework instance over HTTP; it neither owns networking behavior nor creates an independent discovery state.

SNF owns protocol discovery, normalized observations, network-entity resolution, service aggregation, runtime lifecycle, event fan-out, and storage contracts. Device-specific control, application workflows, and home-automation rules are outside SNF.

### Boundaries

| Area | SNF | Consuming application |
| --- | --- | --- |
| Protocol discovery and normalization | Owns | Configures |
| Live observation registry and lifecycle | Owns | Reads/subscribes |
| Network identity resolution and evidence | Owns | May add application knowledge |
| Service/endpoint aggregation | Owns | Uses |
| Storage contracts and optional drivers | Owns | Selects/configures |
| REST/SSE/OpenAPI | Optional SNF adapter | Embeds router if desired |
| Device-specific integrations and commands | Does not own | Owns |
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

- Document whether subscriptions are future-only or include an initial snapshot; initial migration preserves SHA's future-only SSE semantics.
- Define behavior for bounded buffers and slow consumers (initial migration: disconnect slow subscriber rather than block discovery).
- Ensure subscriber registration/unregistration and shutdown are cancellation-safe.
- Document ordering and event types; avoid claiming delivery durability or replay.
- Do not conflate `REMOVED` observation events with proof that physical hardware is offline.

### Identity and entity resolution (subsequent phase)

Keep raw `DiscoveryObservation` records as protocol evidence. Add a separate network-entity projection with provenance for each correlation decision.

- Consolidate advertisements within a protocol only when that protocol supplies defensible identity evidence (e.g., SSDP UDN); preserve distinct services and their lifecycles.
- Cross-protocol correlation must use explicit matching evidence and support uncertainty; **never automatically merge solely on name, IP address, or BLE address**.
- Network entities are not necessarily physical devices. Entity IDs and relationships must remain stable or have documented reconciliation semantics.
- No cryptographic claim should be implied by a field named `verified` unless actual verification exists.
- Identity resolution must be testable without FastAPI and without a database.

### Storage

Retain `ObservationStorage` as the existing historical-observation contract and `InMemoryStorage` as a reference implementation. Live snapshots remain distinct from remembered observations. A persisted record is not evidence of current availability.

Later phases may introduce entity storage, reconciliation, and an optional SQLite driver after deciding persistence keys, schema evolution, restart behavior, and stale-state semantics. No database dependency is required by SNF core.

### Optional dependencies

Keep the base package usable without FastAPI, SSE, or SQL libraries. Provide an `api` extra for HTTP dependencies and optional storage extras when concrete drivers exist. Preserve the existing optional protocol extras. No new server process is required for direct Python usage.

### HTTP surface (initial migration)

Preserve the existing SHA semantics where practical:

- `GET /network/discoveries` — live observations, optional protocol filter.
- `GET /network/discoveries/map` — grouped live observations.
- `GET /network/discoveries/events` — future-only SSE with bounded per-client buffering.
- Health diagnostics may be exposed through a separate route, with runtime-health semantics explicitly documented.

HTTP handlers perform validation and serialization, then delegate to SNF runtime/services. They do not instantiate their own engine. Default examples bind localhost; exposing network inventory remotely requires deliberate authentication and deployment controls.

## Implementation sequence

1. **Architecture review (this ADR):** agree on boundaries, ownership, event and lifecycle contracts.
2. **Consolidation PR:** migrate SHA's generic runtime, subscriber fan-out, service projection, and HTTP schemas/routes into SNF. Preserve behavior; do not implement correlation or SQL in this PR.
3. **Entity-resolution PR:** deterministic, evidence-based protocol consolidation and cross-protocol correlation with provenance and lifecycle tests.
4. **Persistence PR:** explicit durable-inventory and reconciliation contracts; add SQLite only after contract tests.
5. **Real-device validation:** SSDP, mDNS, OpenSLP, BLE, disconnect/reconnect, multiple clients, restart and cancellation behavior.
6. **Retire SHA only after parity:** verify no reusable code or documentation remains solely there; archive before considering deletion.

## Acceptance criteria for consolidation

- Direct Python usage works without installing HTTP dependencies.
- Optional FastAPI router uses the same runtime and live inventory as Python callers.
- Only one discovery-consumer task exists per runtime; multiple SSE subscribers do not duplicate discovery.
- Existing SNF protocol tests and migrated SHA REST/SSE tests pass.
- Event fan-out handles slow clients, disconnects, cancellation, and shutdown.
- API import has no startup/network side effects.
- `py.typed` and strict typing checks are considered for published Python consumers.
- Documentation and examples cover embedding in an existing application.
- No home-automation-specific classes or dependency on SHA are introduced.

## Alternatives considered

1. **Leave API/runtime in SHA:** rejected because generic consumers would reimplement networking infrastructure.
2. **Make SNF a mandatory standalone server:** rejected because it compromises embedding and introduces an unnecessary process boundary.
3. **Make FastAPI mandatory:** rejected because core Python consumers do not need an HTTP stack.
4. **Move correlation into SHA:** rejected as the default because reusable network-entity resolution belongs in SNF; application-specific interpretation remains outside it.
5. **Implement migration, correlation, and persistence together:** rejected due to excessive behavior and contract changes in one PR.

## Consequences and risks

The framework becomes more capable and owns more lifecycle complexity. The implementation must avoid double consumption, unsafe correlation, unbounded queues, blocking slow subscribers, and accidental HTTP exposure. The existing discovery-centric design document and developer guide must be revised after this ADR is accepted; until then, they describe the current implementation rather than the target architecture.
