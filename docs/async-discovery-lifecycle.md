# Async Discovery Lifecycle

This document explains how SNF uses Python's `asyncio` event loop, how plugin coroutines are started and consumed, how observations reach the inventory, and what happens during shutdown.

The implementation described here corresponds to:

- `src/snf/engine.py`
- `src/snf/plugins.py`
- `src/snf/registry.py`
- `src/snf/models.py`
- `src/snf/adapters/`

## 1. The short version

A consumer creates plugin instances and enters the engine's asynchronous context. The engine starts the plugins concurrently. When the consumer begins iterating over `engine.discover()`, the engine creates one asynchronous task per plugin. Each task reads its plugin's async event stream and forwards events to a shared queue. The engine reads that queue, updates the in-memory registry, and yields normalized events to the consumer.

```text
Application
    |
    | async with DiscoveryEngine(plugins)
    v
DiscoveryEngine.__aenter__()
    |
    | asyncio.gather(plugin.start() ...)
    v
All plugins started
    |
    | async for event in engine.discover()
    v
Create one asyncio task per plugin
    |
    +------------------+------------------+
    |                  |                  |
    v                  v                  v
 _pump(SSDP)        _pump(mDNS)         _pump(BLE)
    |                  |                  |
    v                  v                  v
 plugin.discover()  plugin.discover()  plugin.discover()
    |                  |                  |
    +------------------+------------------+
                       |
                       v
                asyncio.Queue
                       |
                       v
                DeviceRegistry.process()
                       |
             +---------+---------+
             |                   |
             v                   v
      normalized event      inventory update
             |
             v
       consumer receives event
```

## 2. Coroutines, tasks, and async iterators

These Python concepts have different responsibilities.

### Coroutine

An `async def` function produces a coroutine when called. A coroutine describes asynchronous work, but calling it does not by itself run it to completion.

For example:

```python
async def initialize():
    await open_resource()

pending = initialize()  # Coroutine object; not yet awaited or scheduled.
await pending           # Run it as part of the current coroutine.
```

SNF plugin lifecycle methods such as `start()` and `stop()` are coroutines.

### Task

An `asyncio.Task` schedules a coroutine on the running event loop. It allows multiple asynchronous operations to make progress concurrently.

SNF uses `asyncio.gather()` to start plugin coroutines together and `asyncio.create_task()` to run each plugin event pump concurrently.

### Async iterator and async generator

An async iterator provides values over time and is consumed with `async for`.

A plugin's `discover()` method returns an `AsyncIterator[DiscoveryEvent]`. Implementations commonly use an async generator:

```python
async def discover(self):
    while self.running:
        event = await self.next_observation()
        yield event
```

Each `yield` hands one event to the consumer of that iterator. The generator can then suspend while waiting for the next observation.

### await is not the same as creating a task

`await operation()` suspends the current coroutine until that operation completes, allowing other scheduled tasks to run in the meantime.

`asyncio.create_task(operation())` schedules the coroutine independently so the caller can continue while it runs.

SNF uses both patterns: startup awaits a gathered set of coroutines; discovery creates independent pump tasks.

## 3. Entry point: the application's event loop

A normal Python application starts the asynchronous program with `asyncio.run()`:

```python
import asyncio

async def main():
    ...

asyncio.run(main())
```

`asyncio.run()` creates and manages the event loop for the main coroutine. Inside that loop, SNF can schedule plugin coroutines and tasks.

Do not call `asyncio.run()` from inside an already-running event loop, such as inside an async web handler or notebook cell. In those environments, await the application coroutine directly.

## 4. Engine startup

The engine is an asynchronous context manager:

```python
async with DiscoveryEngine(plugins) as engine:
    ...
```

Entering the context calls `DiscoveryEngine.__aenter__()`.

The engine:

1. Rejects a second concurrent start of the same engine instance.
2. Calls every plugin's `start()`.
3. Awaits them through `asyncio.gather(..., return_exceptions=True)`.
4. If startup failures occurred, attempts to stop all configured plugins and raises the first failure.
5. Marks itself as started only after all plugin starts succeed.

Using `gather()` means startup operations can overlap. For example, an mDNS adapter may initialize its browser while a BLE adapter starts scanning. The engine does not start one adapter and wait for its full discovery lifetime before starting the next.

A plugin's `start()` should initialize resources and return. It should not contain an endless discovery loop. Continuous observation belongs in `discover()` or in background tasks owned by that plugin.

## 5. Discovery begins when the iterator is consumed

After the context is entered, the consumer calls:

```python
async for event in engine.discover():
    ...
```

The body of `DiscoveryEngine.discover()` runs as the async iterator is consumed. It verifies that the engine is started, creates an `asyncio.Queue`, and creates one task for each configured plugin:

```python
asyncio.create_task(
    self._pump(plugin, queue),
    name=f"snf:{plugin.name}",
)
```

Each pump executes concurrently. It consumes one plugin's iterator:

```python
async for event in plugin.discover():
    await queue.put(event)
```

The plugin does not call the engine's registry directly. It yields a normalized event; the pump forwards that event to the shared queue.

### Why use a queue?

Different protocols produce observations at different times and rates:

- SSDP produces observations after periodic multicast searches.
- mDNS produces observations in response to service-browser callbacks.
- BLE can produce a continuous stream of advertisements.
- SLP periodically queries service types and service URLs.

The queue decouples each producer from the engine's single event-consumption loop. A plugin pump can forward an event without needing to know which other plugin produced the previous event.

The queue is currently an unbounded `asyncio.Queue`. This keeps the implementation simple, but it means a sustained producer rate higher than the consumer rate can increase memory use. Queue backpressure and bounded-queue policy are future design considerations.

## 6. How adapter observations become events

Each adapter translates its protocol's data into the shared domain model.

Examples:

- SSDP parses response headers and builds a device with an IP endpoint and service metadata.
- mDNS receives a Zeroconf service-state callback, schedules asynchronous resolution on the event loop, and places the normalized event on its internal queue.
- BLE receives Bleak advertisement callbacks, normalizes advertisement data, and puts events on its internal queue. A separate expiry task emits removals for addresses that have not been observed within the configured timeout.
- SLP invokes OpenSLP's `slptool` asynchronously, parses returned service URLs, and yields newly observed services.

Some adapters use callbacks internally, but the plugin boundary remains an async iterator. The engine does not need to know whether the adapter is callback-driven or polling-driven.

## 7. Event normalization and inventory update

The engine's discovery loop reads an item from the shared queue.

For a normal `DiscoveryEvent`, it calls:

```python
normalized = self._registry.process(item)
```

The registry key is:

```python
(device.protocol, device.identifier)
```

The registry applies these rules:

| Incoming observation | Registry state | Result yielded to consumer |
| --- | --- | --- |
| First observation for an identity | No previous record | `ADDED` |
| Same identity and identical device data | Existing identical record | No event |
| Same identity with changed device data | Existing different record | `UPDATED` |
| Removal for a known identity | Existing record | `REMOVED`, with the previous stored device |
| Removal for an unknown identity | No previous record | No event |

This means adapters do not need to coordinate with each other or directly mutate the inventory.

### Where is the data stored?

The current inventory is held in the engine's `DeviceRegistry`, which is an in-memory `OrderedDict` keyed by `(protocol, identifier)`.

The public accessors are:

```python
engine.devices
engine.get_device(protocol, identifier)
```

- `engine.devices` returns an immutable tuple snapshot of the current records.
- `engine.get_device()` returns one current record or `None`.
- The default maximum size is 4,096 entries; the engine constructor can override it with `dedupe_cache_size`.

When the maximum is exceeded, the oldest registry entry is removed to keep the inventory bounded. This capacity eviction currently does not emit a lifecycle event.

There is no database, file, or durable storage in the current implementation. The inventory exists only for the lifetime of the process/engine and is lost when the application exits.

## 8. How the consumer receives an event

The engine yields an event only when the registry returns a meaningful normalized event:

```python
async with DiscoveryEngine(plugins) as engine:
    async for event in engine.discover():
        print(event.state, event.device)
        print("Current inventory:", engine.devices)
```

The consumer sees one merged stream. It does not need to create one loop per protocol.

The event stream is not a complete history. It reports changes observed during the current discovery run, while `engine.devices` represents the current in-memory inventory.

## 9. How a plugin pump ends

When a plugin's `discover()` iterator finishes, its pump places an internal completion sentinel (`_DONE`) on the shared queue.

The engine counts how many plugin pumps have completed. The discovery iterator ends after all pumps have completed.

For continuous adapters such as mDNS and BLE, the iterator normally remains active until the adapter is stopped or its stream is otherwise closed. Polling adapters such as SSDP and SLP also continue their periodic loops until stopped.

If a plugin pump raises an exception, the engine logs the failure and ends that pump. Other pumps continue. The engine does not currently forward a structured plugin-failure event to the application.

## 10. Shutdown and cancellation

When the application leaves the `async with` block, Python calls `DiscoveryEngine.__aexit__()`, which calls `stop()`.

The engine:

1. Marks itself as no longer started.
2. Calls every plugin's `stop()` in reverse plugin order, concurrently.
3. Logs any plugin shutdown failures while continuing to stop the remaining plugins.

The discovery iterator also has a `finally` block. If the consumer cancels iteration or exits while pumps are active, the engine cancels unfinished pump tasks and awaits their completion.

Plugins must cooperate with this lifecycle:

- A blocking operation must have a timeout or a cancellation strategy.
- Background tasks created by a plugin must be tracked and cancelled/awaited in `stop()`.
- Callbacks should not continue scheduling work after shutdown.
- Queue-based iterators should be unblocked when stopped.
- Resources must be closed even if startup only partially completed.

This is why the context-manager pattern is preferred over manually calling `start()` and `stop()`.

## 11. Important distinctions and current limitations

### Discovery is not a connection

An `Endpoint` is a locator discovered from an advertisement or response. It does not mean SNF has connected to the device or verified that the endpoint is reachable.

### Removal is protocol-specific evidence

An mDNS service removal, a BLE advertisement timeout, and a missing SLP query result are not equivalent signals. The current adapters also have different removal/expiry behavior. Consumers should not infer that a physical device has powered off solely from one removal event.

### Protocol identities are not merged

If SSDP and mDNS discover the same physical device, the registry keeps separate records because their protocol-scoped identities differ. Cross-protocol correlation belongs in a separate layer with stronger evidence.

### Inventory is not persistent

The registry is process-local. Restarting the application starts with an empty inventory and discovery repopulates it.

### The queue is not currently bounded

The engine's shared event queue is unbounded. The inventory itself is bounded, but that does not bound the number of pending events waiting in the queue.

## 12. Practical debugging

Enable DEBUG logging for SNF:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
```

Useful log messages include:

- `Discovery pump started for plugin ...`: the engine created and started consuming that plugin's stream.
- `Plugin ... yielded ...`: the plugin pump received a normalized event.
- Adapter-specific messages: protocol searches, service callbacks, BLE scanner startup, and so on.
- `Discovery plugin ... failed`: the pump caught an exception and ended that stream.
- `Discovery pump stopped ...`: the pump exited.

A pump-start message does not prove that a device has been discovered. It only confirms that the engine is consuming that plugin's iterator. Some protocols are quiet until a device advertises or responds, and mDNS is event-driven rather than a repeated search loop.
