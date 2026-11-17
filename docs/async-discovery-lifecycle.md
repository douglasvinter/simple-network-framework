# Async Discovery Lifecycle

SNF uses one `asyncio` event loop for concurrent protocol discovery. See [Architecture](architecture.md) for component boundaries and [Developer Guide](developer-guide.md) for runnable examples.

## Direct engine usage

```text
Application: async for event in engine.discover()
                         │
                  DiscoveryEngine
                         │
           ┌─────────────┼─────────────┐
           │             │             │
       SSDP pump      mDNS pump      BLE / SLP pumps
           └─────────────┼─────────────┘
                         │
                   asyncio.Queue
                         │
               ObservationRegistry
                         │
                  normalized event
                         │
                     consumer
```

1. `async with DiscoveryEngine(...)` starts plugins concurrently.
2. Iterating `engine.discover()` creates one pump task per started plugin. **Entering the context alone does not consume discovery events.**
3. Each pump forwards events to the shared queue. The engine normalizes events, updates the live registry, writes ADDED/UPDATED observations to injected storage, and yields events.
4. Leaving the context stops plugins and releases resources.

An async iterator suspends between events; `await` yields control to the loop; `asyncio.create_task()` schedules independent work. Plugin `start()` initializes resources and returns—continuous observation belongs in `discover()`.

## Background runtime

```text
Python application / FastAPI lifespan
                 │
           NetworkRuntime
                 │
       one engine consumer task
                 │
           DiscoveryEngine
                 │
           normalized events
                 │
          subscriber fan-out
          ┌──────┴──────┐
       Python          SSE clients
     subscriber     (bounded queues each)
```

`async with NetworkRuntime(...)` starts the single engine consumer automatically. `snapshot()` and `observation_map()` read the same live registry. `subscribe()` returns **future-only** events, optionally filtered by protocol; there is no replay. Each subscriber has a bounded queue; a slow subscriber is disconnected rather than blocking discovery. Close subscriptions when finished.

On shutdown, the runtime cancels its consumer, closes subscribers, and stops the engine. The engine's internal merge queue is currently unbounded. A plugin pump may fail while other plugins continue; `runtime.running` only indicates whether the consumer task is alive.

## Observation semantics

- `ADDED`: new protocol-scoped identity; `UPDATED`: changed data; unchanged duplicates are suppressed; `REMOVED`: adapter-reported removal.
- Registry identity is `(protocol, identifier)`. The map groups observations by those keys; it **does not correlate physical devices**.
- Remembered storage entries are not proof of live availability. A `REMOVED` event does not automatically delete remembered history.
- Discovery is evidence, not proof that a device is online or an endpoint is safe to contact.

## Troubleshooting

Configure `logging.getLogger("snf").setLevel(logging.DEBUG)` in the host application. A pump-start log means the stream is being consumed, not that any device responded. Plugin failures are logged; no per-plugin health report exists yet. See [Logging](logging.md).
