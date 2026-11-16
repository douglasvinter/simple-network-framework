# Inventory storage contract

SNF requires a storage driver when constructing `DiscoveryEngine`. No disk or
database implementation is bundled; `InMemoryStorage` is the reference driver.

```python
from snf import DiscoveryEngine, InMemoryStorage, create_plugins

storage = InMemoryStorage()
async with DiscoveryEngine(create_plugins(), storage=storage) as engine:
    async for event in engine.discover():
        live_mdns = engine.snapshot(protocol="mdns")
        remembered_mdns = await engine.saved_devices(protocol="mdns")
```

The live `DeviceRegistry` remains responsible for event normalization,
deduplication, and synchronous `snapshot()` / `get_device()` operations.
The storage driver remembers discovered devices, keyed by
`(protocol, identifier)`. Discovery removals do not delete historical records;
call `storage.remove(protocol, identifier)` explicitly to forget one.
The engine does not preload historical devices as online.

## Custom storage

Implement the structural `InventoryStorage` protocol, without inheriting
from a base class:

```python
from snf import Device, InventoryStorage

class MyStorage:
    async def get(self, protocol: str, identifier: str) -> Device | None: ...
    async def upsert(self, device: Device) -> None: ...
    async def remove(self, protocol: str, identifier: str) -> None: ...
    async def snapshot(
        self, *, protocol: str | None = None
    ) -> tuple[Device, ...]: ...

storage: InventoryStorage = MyStorage()
```

These operations are async so callers may implement non-blocking persistence.
The engine awaits each `upsert` for normalized added/updated observations.
By default, storage write errors are logged and discovery continues; setting
`strict=True` propagates write errors. The caller owns the driver's lifecycle
and must open/close any external connections as appropriate.

`engine.devices` and `engine.snapshot()` represent only devices observed
during the current discovery session. `engine.saved_devices()` reads from
the configured storage, including records from previous sessions if the driver
supports persistence. Reusing the same `InMemoryStorage` instance preserves
records across engine instances, but not process restarts.
